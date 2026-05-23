"""Tool-calling literature assistant router."""
from __future__ import annotations

import json
import hashlib
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for import_path in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from auth.dependencies import current_user
try:
    from backend.routers import reading
    from backend.utils.api_key import validate_deepseek_key
except ModuleNotFoundError:  # Support the backend/ working directory used by local checks.
    from routers import reading
    from utils.api_key import validate_deepseek_key
from db import get_db
from db.models import (
    AgentActionProposal,
    AgentMessage,
    AgentSession,
    Artifact,
    BibEntry,
    File,
    Job,
    JobBibEntry,
    ReadingItem,
    User,
    UserSettings,
)
from db.utils import title_match_score
from routers.upload import ALLOWED_EXTENSIONS, detect_file_type
from upload_storage import build_storage_path

router = APIRouter()

MODEL = "deepseek-v4-flash"
MAX_TOOL_ROUNDS = 8


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AgentTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(default="", max_length=30000)


class AgentChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=8000)
    api_key: Optional[str] = None
    history: list[AgentTurn] = Field(default_factory=list, max_length=12)


class AgentSettingsRequest(BaseModel):
    input_folder_path: str = Field(default="", max_length=2000)


class AgentProposalConfirmRequest(BaseModel):
    api_key: Optional[str] = None


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _dt(value) -> str | None:
    return value.isoformat() if value else None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _session_title(message: str) -> str:
    title = " ".join(message.strip().split())
    return title[:40] or "AI 文献助手会话"


async def _get_session(db: AsyncSession, user: User, session_id: str) -> AgentSession | None:
    return (
        await db.execute(
            select(AgentSession).where(
                AgentSession.id == session_id,
                AgentSession.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()


async def _ensure_session(db: AsyncSession, user: User, req: AgentChatRequest) -> AgentSession:
    if req.session_id:
        existing = await _get_session(db, user, req.session_id)
        if existing is not None:
            return existing
    session = AgentSession(
        id=str(uuid.uuid4()),
        owner_user_id=user.id,
        title=_session_title(req.message),
        status="active",
        last_state_json="{}",
        expires_at=reading.compute_expires_at(user),
    )
    db.add(session)
    await db.flush()
    return session


async def _next_message_order(db: AsyncSession, session_id: str) -> int:
    value = (
        await db.execute(
            select(func.coalesce(func.max(AgentMessage.sort_order), 0)).where(
                AgentMessage.session_id == session_id
            )
        )
    ).scalar_one()
    return int(value or 0) + 1


async def _save_agent_message(
    db: AsyncSession,
    user: User,
    session: AgentSession,
    *,
    role: str,
    event_type: str,
    content: str = "",
    tool_name: str | None = None,
    payload: Any = None,
) -> AgentMessage:
    message = AgentMessage(
        id=str(uuid.uuid4()),
        session_id=session.id,
        owner_user_id=user.id,
        role=role,
        event_type=event_type,
        tool_name=tool_name,
        content=content or "",
        payload_json=_json_dumps(payload) if payload is not None else None,
        sort_order=await _next_message_order(db, session.id),
        expires_at=reading.compute_expires_at(user),
    )
    db.add(message)
    session.updated_at = utcnow_naive()
    await db.flush()
    return message


def _message_payload(message: AgentMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "event_type": message.event_type,
        "tool_name": message.tool_name,
        "content": message.content,
        "payload": _json_loads(message.payload_json, None),
        "sort_order": message.sort_order,
        "created_at": _dt(message.created_at),
    }


async def _update_session_state(
    db: AsyncSession,
    session: AgentSession,
    *,
    key: str,
    value: Any,
) -> None:
    state = _json_loads(session.last_state_json, {}) or {}
    state[key] = value
    session.last_state_json = _json_dumps(state)
    session.updated_at = utcnow_naive()
    await db.flush()


async def _create_proposal(
    db: AsyncSession,
    user: User,
    session: AgentSession,
    *,
    action_type: str,
    arguments: dict[str, Any],
    preview: dict[str, Any],
) -> dict[str, Any]:
    proposal = AgentActionProposal(
        id=str(uuid.uuid4()),
        session_id=session.id,
        owner_user_id=user.id,
        action_type=action_type,
        status="pending",
        arguments_json=_json_dumps(arguments),
        preview_json=_json_dumps(preview),
        expires_at=reading.compute_expires_at(user),
    )
    db.add(proposal)
    await db.flush()
    payload = {
        "proposal_id": proposal.id,
        "action_type": action_type,
        "status": proposal.status,
        "arguments": arguments,
        "preview": preview,
    }
    await _save_agent_message(
        db,
        user,
        session,
        role="tool",
        event_type="proposal",
        tool_name=action_type,
        payload=payload,
    )
    await _update_session_state(db, session, key="last_proposal", value=payload)
    return payload


async def _proposal_payload(proposal: AgentActionProposal) -> dict[str, Any]:
    return {
        "proposal_id": proposal.id,
        "session_id": proposal.session_id,
        "action_type": proposal.action_type,
        "status": proposal.status,
        "arguments": _json_loads(proposal.arguments_json, {}) or {},
        "preview": _json_loads(proposal.preview_json, {}) or {},
        "result": _json_loads(proposal.result_json, None),
        "created_at": _dt(proposal.created_at),
        "confirmed_at": _dt(proposal.confirmed_at),
    }


def _load_preferences(settings: UserSettings | None) -> dict[str, Any]:
    if not settings or not settings.preferences_json:
        return {}
    try:
        parsed = json.loads(settings.preferences_json)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def get_agent_preferences(db: AsyncSession, user: User) -> dict[str, Any]:
    settings = await db.get(UserSettings, user.id)
    prefs = _load_preferences(settings)
    agent_prefs = prefs.get("agent") if isinstance(prefs.get("agent"), dict) else {}
    return {
        "input_folder_path": str(agent_prefs.get("input_folder_path") or ""),
    }


async def save_agent_preferences(db: AsyncSession, user: User, agent_prefs: dict[str, Any]) -> dict[str, Any]:
    settings = await db.get(UserSettings, user.id)
    prefs = _load_preferences(settings)
    prefs["agent"] = {
        **(prefs.get("agent") if isinstance(prefs.get("agent"), dict) else {}),
        **agent_prefs,
    }
    if settings is None:
        settings = UserSettings(user_id=user.id, preferences_json=json.dumps(prefs, ensure_ascii=False))
        db.add(settings)
    else:
        settings.preferences_json = json.dumps(prefs, ensure_ascii=False)
    await db.commit()
    return await get_agent_preferences(db, user)


def _normalize_input_folder(raw_path: str) -> str:
    text = (raw_path or "").strip().strip('"')
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError("请输入绝对路径。")
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError("文件夹不存在或不是有效目录。")
    return str(resolved)


@router.get("/settings")
async def get_agent_settings(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_agent_preferences(db, user)


@router.put("/settings")
async def update_agent_settings(
    req: AgentSettingsRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        input_folder_path = _normalize_input_folder(req.input_folder_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return await save_agent_preferences(db, user, {"input_folder_path": input_folder_path})


@router.get("/sessions")
async def list_agent_sessions(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(AgentSession)
            .where(AgentSession.owner_user_id == user.id, AgentSession.status == "active")
            .order_by(desc(AgentSession.updated_at))
            .limit(30)
        )
    ).scalars().all()
    return [
        {
            "id": row.id,
            "title": row.title,
            "status": row.status,
            "created_at": _dt(row.created_at),
            "updated_at": _dt(row.updated_at),
            "last_state": _json_loads(row.last_state_json, {}) or {},
        }
        for row in rows
    ]


@router.post("/sessions")
async def create_agent_session(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = AgentSession(
        id=str(uuid.uuid4()),
        owner_user_id=user.id,
        title="AI 文献助手会话",
        status="active",
        last_state_json="{}",
        expires_at=reading.compute_expires_at(user),
    )
    db.add(session)
    await db.commit()
    return {"id": session.id, "title": session.title}


@router.get("/sessions/{session_id}")
async def get_agent_session(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(db, user, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Agent session not found")
    messages = (
        await db.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == session.id, AgentMessage.owner_user_id == user.id)
            .order_by(AgentMessage.sort_order.asc())
            .limit(200)
        )
    ).scalars().all()
    proposals = (
        await db.execute(
            select(AgentActionProposal)
            .where(AgentActionProposal.session_id == session.id, AgentActionProposal.owner_user_id == user.id)
            .order_by(desc(AgentActionProposal.created_at))
            .limit(30)
        )
    ).scalars().all()
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "created_at": _dt(session.created_at),
        "updated_at": _dt(session.updated_at),
        "last_state": _json_loads(session.last_state_json, {}) or {},
        "messages": [_message_payload(message) for message in messages],
        "proposals": [await _proposal_payload(proposal) for proposal in proposals],
    }


@router.patch("/sessions/{session_id}/archive")
async def archive_agent_session(
    session_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_session(db, user, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Agent session not found")
    session.status = "archived"
    await db.commit()
    return {"ok": True}


async def _execute_proposal_action(
    db: AsyncSession,
    user: User,
    proposal: AgentActionProposal,
    api_key: str,
) -> dict[str, Any]:
    args = _json_loads(proposal.arguments_json, {}) or {}
    if proposal.action_type == "start_reading":
        return await tool_start_reading(db, user, api_key=api_key, **args)
    if proposal.action_type == "start_batch_reading":
        return await tool_start_batch_reading(db, user, api_key=api_key, **args)
    if proposal.action_type == "import_folder_and_start_reading":
        return await tool_import_folder_and_start_reading(db, user, api_key=api_key, **args)
    return {"error": f"unknown_proposal_action:{proposal.action_type}"}


@router.post("/proposals/{proposal_id}/confirm")
async def confirm_agent_proposal(
    proposal_id: str,
    req: AgentProposalConfirmRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        api_key = validate_deepseek_key(req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    proposal = (
        await db.execute(
            select(AgentActionProposal).where(
                AgentActionProposal.id == proposal_id,
                AgentActionProposal.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is {proposal.status}")
    session = await _get_session(db, user, proposal.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Agent session not found")

    proposal.status = "confirmed"
    proposal.confirmed_at = utcnow_naive()
    await _save_agent_message(
        db,
        user,
        session,
        role="user",
        event_type="confirmation",
        content="确认执行",
        tool_name=proposal.action_type,
        payload={"proposal_id": proposal.id},
    )
    result = await _execute_proposal_action(db, user, proposal, api_key)
    proposal.status = "failed" if isinstance(result, dict) and result.get("error") else "executed"
    proposal.result_json = _json_dumps(result)
    await _save_agent_message(
        db,
        user,
        session,
        role="tool",
        event_type="tool_result",
        tool_name=proposal.action_type,
        payload={"proposal_id": proposal.id, "execution_result": result},
    )
    await _update_session_state(db, session, key="last_execution", value={"proposal_id": proposal.id, "result": result})
    await db.commit()
    return {"proposal": await _proposal_payload(proposal), "result": result}


@router.post("/proposals/{proposal_id}/reject")
async def reject_agent_proposal(
    proposal_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    proposal = (
        await db.execute(
            select(AgentActionProposal).where(
                AgentActionProposal.id == proposal_id,
                AgentActionProposal.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail=f"Proposal is {proposal.status}")
    session = await _get_session(db, user, proposal.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Agent session not found")
    proposal.status = "rejected"
    await _save_agent_message(
        db,
        user,
        session,
        role="user",
        event_type="confirmation",
        content="取消执行",
        tool_name=proposal.action_type,
        payload={"proposal_id": proposal.id},
    )
    await db.commit()
    return {"proposal": await _proposal_payload(proposal)}


def _entry_summary(entry: BibEntry, file_record: File | None = None) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "title": entry.title,
        "authors": _json_list(entry.authors_json),
        "year": entry.year,
        "journal": entry.journal,
        "doi": entry.doi,
        "keywords": _json_list(entry.keywords_json),
        "tags": _json_list(entry.user_tags_json),
        "reading_status": entry.reading_status,
        "source_file_id": entry.source_file_id,
        "source_file_name": file_record.original_name if file_record else None,
        "abstract": (entry.abstract or "")[:1200],
        "updated_at": _dt(entry.updated_at),
    }


async def _owned_entries(db: AsyncSession, user: User, entry_ids: list[str]) -> list[BibEntry]:
    if not entry_ids:
        return []
    rows = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == user.id,
                BibEntry.id.in_(entry_ids),
            )
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    return [by_id[entry_id] for entry_id in entry_ids if entry_id in by_id]


async def tool_search_library(
    db: AsyncSession,
    user: User,
    *,
    query: str = "",
    reading_status: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    limit = max(1, int(limit or 50))
    stmt = select(BibEntry, File).outerjoin(File, File.id == BibEntry.source_file_id).where(
        BibEntry.owner_user_id == user.id
    )
    if query.strip():
        like = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                BibEntry.title.ilike(like),
                BibEntry.abstract.ilike(like),
                BibEntry.journal.ilike(like),
                BibEntry.keywords_json.ilike(like),
                BibEntry.user_tags_json.ilike(like),
            )
        )
    if reading_status.strip():
        stmt = stmt.where(BibEntry.reading_status == reading_status.strip())
    rows = (
        await db.execute(stmt.order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc()).limit(limit))
    ).all()
    return {
        "count": len(rows),
        "entries": [_entry_summary(entry, file_record) for entry, file_record in rows],
    }


async def tool_get_entry_detail(db: AsyncSession, user: User, *, entry_id: str) -> dict[str, Any]:
    entry = (
        await db.execute(
            select(BibEntry).where(BibEntry.id == entry_id, BibEntry.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if not entry:
        return {"error": "entry_not_found"}
    file_record = await db.get(File, entry.source_file_id) if entry.source_file_id else None
    jobs = (
        await db.execute(
            select(Job)
            .join(JobBibEntry, JobBibEntry.job_id == Job.id)
            .where(Job.owner_user_id == user.id, JobBibEntry.bib_entry_id == entry.id)
            .order_by(Job.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    return {
        "entry": _entry_summary(entry, file_record),
        "note": entry.user_note,
        "timeline": [
            {
                "job_id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "progress": job.progress,
                "stage": job.current_stage,
                "created_at": _dt(job.created_at),
                "finished_at": _dt(job.finished_at),
            }
            for job in jobs
        ],
    }


async def tool_get_reading_context(
    db: AsyncSession,
    user: User,
    *,
    entry_ids: list[str],
    mode: str = "",
    max_chars_per_item: int = 2500,
) -> dict[str, Any]:
    entries = await _owned_entries(db, user, entry_ids)
    if not entries:
        return {"error": "no_owned_entries"}
    max_chars_per_item = max(300, min(int(max_chars_per_item or 2500), 8000))
    stmt = select(ReadingItem).where(
        ReadingItem.owner_user_id == user.id,
        ReadingItem.bib_entry_id.in_([entry.id for entry in entries]),
    )
    if mode.strip() in {"long", "quant", "qual"}:
        stmt = stmt.where(ReadingItem.mode == mode.strip())
    items = (
        await db.execute(stmt.order_by(ReadingItem.bib_entry_id, ReadingItem.mode, ReadingItem.sort_order))
    ).scalars().all()
    entry_map = {entry.id: _entry_summary(entry) for entry in entries}
    return {
        "entries": list(entry_map.values()),
        "items": [
            {
                "entry_id": item.bib_entry_id,
                "title": entry_map.get(item.bib_entry_id, {}).get("title"),
                "mode": item.mode,
                "section_type": item.section_type,
                "item_key": item.item_key,
                "item_label": item.item_label,
                "content": item.content[:max_chars_per_item],
            }
            for item in items
        ],
    }


async def tool_start_reading(
    db: AsyncSession,
    user: User,
    *,
    api_key: str,
    mode: str,
    file_id: str = "",
    entry_id: str = "",
    analysis_dims: list[str] | None = None,
    custom_question: str | None = None,
    extraction_method: str = "full",
    conflict_resolution: str = "check",
) -> dict[str, Any]:
    if mode not in {"long", "quant", "qual"}:
        return {"error": "mode_must_be_long_quant_or_qual"}
    if not file_id and entry_id:
        entry = (
            await db.execute(
                select(BibEntry).where(BibEntry.id == entry_id, BibEntry.owner_user_id == user.id)
            )
        ).scalar_one_or_none()
        file_id = entry.source_file_id if entry else ""
    if not file_id:
        return {"error": "file_id_required", "hint": "Use search_library or get_entry_detail to find source_file_id."}

    if mode == "long":
        request = reading.LongContextRequest(
            file_id=file_id,
            analysis_dims=analysis_dims or [],
            custom_question=custom_question,
            extraction_method=extraction_method or "full",
            api_key=api_key,
            conflict_resolution=conflict_resolution,
        )
        try:
            return await reading.start_long_context(request, user=user, db=db)
        except HTTPException as exc:
            return {"error": "start_reading_failed", "status_code": exc.status_code, "detail": exc.detail}
    request = reading.SimpleReadingRequest(
        file_id=file_id,
        api_key=api_key,
        conflict_resolution=conflict_resolution,
    )
    try:
        if mode == "quant":
            return await reading.start_quant(request, user=user, db=db)
        return await reading.start_qual(request, user=user, db=db)
    except HTTPException as exc:
        return {"error": "start_reading_failed", "status_code": exc.status_code, "detail": exc.detail}


async def tool_start_batch_reading(
    db: AsyncSession,
    user: User,
    *,
    api_key: str,
    mode: str,
    file_ids: list[str],
    analysis_dims: list[str] | None = None,
    custom_question: str | None = None,
    extraction_method: str = "full",
    conflict_resolution: str = "skip",
) -> dict[str, Any]:
    if mode not in {"long", "quant", "qual"}:
        return {"error": "mode_must_be_long_quant_or_qual"}
    request = reading.BatchReadingRequest(
        file_ids=file_ids,
        mode=mode,
        analysis_dims=analysis_dims or [],
        custom_question=custom_question,
        extraction_method=extraction_method or "full",
        api_key=api_key,
        conflict_resolution=conflict_resolution,
    )
    try:
        return await reading.start_batch_reading(request, user=user, db=db)
    except HTTPException as exc:
        return {"error": "start_batch_reading_failed", "status_code": exc.status_code, "detail": exc.detail}


async def tool_get_job_status(db: AsyncSession, user: User, *, job_id: str) -> dict[str, Any]:
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.owner_user_id == user.id))
    ).scalar_one_or_none()
    if not job:
        return {"error": "job_not_found"}
    artifacts = (
        await db.execute(
            select(Artifact)
            .where(Artifact.job_id == job.id, Artifact.owner_user_id == user.id)
            .order_by(Artifact.sort_order, Artifact.id)
        )
    ).scalars().all()
    return {
        "job_id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "stage": job.current_stage,
        "error": job.error_msg,
        "created_at": _dt(job.created_at),
        "finished_at": _dt(job.finished_at),
        "artifacts": [
            {
                "artifact_type": artifact.artifact_type,
                "filename": artifact.filename,
                "storage_path": artifact.storage_path,
            }
            for artifact in artifacts
        ],
    }


def _file_md5_and_sample(path: Path) -> tuple[str, int, bytes]:
    hasher = hashlib.md5()
    size_bytes = 0
    sample = b""
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            if not sample:
                sample = chunk[:4096]
            hasher.update(chunk)
            size_bytes += len(chunk)
    return hasher.hexdigest(), size_bytes, sample


def _extract_preview(path: Path, file_type: str, max_chars: int = 2200) -> str:
    if file_type == "markdown":
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    if file_type == "pdf":
        try:
            import pdfplumber

            parts: list[str] = []
            with pdfplumber.open(str(path)) as pdf:
                for page in pdf.pages[:2]:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts)[:max_chars]
        except Exception:
            return ""
    return ""


async def _import_source_file(
    db: AsyncSession,
    user: User,
    source_path: Path,
) -> dict[str, Any]:
    suffix = source_path.suffix.lower()
    if suffix not in {".pdf", ".md", ".markdown"}:
        return {"status": "skipped", "reason": "unsupported_for_reading", "path": str(source_path)}
    if suffix not in ALLOWED_EXTENSIONS:
        return {"status": "skipped", "reason": "unsupported_extension", "path": str(source_path)}

    md5_hash, size_bytes, sample = _file_md5_and_sample(source_path)
    if size_bytes <= 0:
        return {"status": "skipped", "reason": "empty_file", "path": str(source_path)}
    file_type = detect_file_type(source_path.name, sample)
    if file_type not in {"pdf", "markdown"}:
        return {"status": "skipped", "reason": "unsupported_for_reading", "path": str(source_path)}

    existing = (
        await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
    ).scalar_one_or_none()
    if existing is not None:
        bib_entry = await reading.get_or_create_bib_entry(db, user, existing)
        await db.commit()
        return {
            "status": "deduplicated",
            "file_id": existing.id,
            "entry_id": bib_entry.id,
            "title": bib_entry.title,
            "filename": existing.original_name,
            "preview": _extract_preview(source_path, file_type),
        }

    file_id = str(uuid.uuid4())
    final_path, storage_path = build_storage_path(user.id, file_id, suffix)
    shutil.copy2(source_path, final_path)
    record = File(
        id=file_id,
        owner_user_id=user.id,
        original_name=source_path.name,
        file_type=file_type,
        storage_path=storage_path,
        size_bytes=size_bytes,
        md5=md5_hash,
        expires_at=reading.compute_expires_at(user),
    )
    db.add(record)
    try:
        bib_entry = await reading.get_or_create_bib_entry(db, user, record)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if final_path.exists():
            final_path.unlink()
        existing = (
            await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
        ).scalar_one_or_none()
        if existing is None:
            raise
        bib_entry = await reading.get_or_create_bib_entry(db, user, existing)
        await db.commit()
        return {
            "status": "deduplicated",
            "file_id": existing.id,
            "entry_id": bib_entry.id,
            "title": bib_entry.title,
            "filename": existing.original_name,
            "preview": _extract_preview(source_path, file_type),
        }

    return {
        "status": "imported",
        "file_id": record.id,
        "entry_id": bib_entry.id,
        "title": bib_entry.title,
        "filename": record.original_name,
        "preview": _extract_preview(source_path, file_type),
    }


def _collect_folder_files(input_folder: Path, recursive: bool, max_files: int) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files = [
        path
        for path in input_folder.glob(pattern)
        if path.is_file() and path.suffix.lower() in {".pdf", ".md", ".markdown"}
    ]
    files.sort(key=lambda path: path.name.lower())
    return files[: max(1, min(max_files, 100))]


def _classify_relevance(api_key: str, topic: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0),
    )
    prompt = {
        "topic": topic,
        "candidates": [
            {
                "entry_id": item["entry_id"],
                "file_id": item["file_id"],
                "title": item["title"],
                "filename": item["filename"],
                "preview": item.get("preview", ""),
            }
            for item in candidates
        ],
    }
    response = client.chat.completions.create(
        model=MODEL,
        extra_body={"thinking": {"type": "disabled"}},
        messages=[
            {
                "role": "system",
                "content": (
                    "你是学术文献筛选助手。根据主题判断候选文献是否相关。"
                    "只返回 JSON：{\"items\":[{\"entry_id\":\"...\",\"relevant\":true,"
                    "\"confidence\":0.0到1.0,\"reason\":\"简短理由\"}]}。"
                ),
            },
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=5000,
    )
    content = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    rows = parsed.get("items") if isinstance(parsed, dict) else []
    return rows if isinstance(rows, list) else []


def _is_all_topic(topic: str) -> bool:
    return topic.strip().casefold() in {"*", "all", "全部", "所有", "全选", "全部文献", "所有文献"}


async def tool_scan_input_folder(
    db: AsyncSession,
    user: User,
    *,
    api_key: str,
    topic: str = "*",
    recursive: bool = False,
    max_files: int = 50,
    confidence_threshold: float = 0.55,
) -> dict[str, Any]:
    prefs = await get_agent_preferences(db, user)
    input_folder_path = prefs.get("input_folder_path") or ""
    if not input_folder_path:
        return {"error": "input_folder_not_configured", "hint": "请先在设置里保存 input 文件夹白名单路径。"}
    input_folder = Path(input_folder_path)
    if not input_folder.exists() or not input_folder.is_dir():
        return {"error": "input_folder_missing", "path": input_folder_path}

    files = _collect_folder_files(input_folder, recursive, max_files)
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index, source_path in enumerate(files, start=1):
        try:
            md5_hash, size_bytes, sample = _file_md5_and_sample(source_path)
            file_type = detect_file_type(source_path.name, sample)
        except Exception as exc:
            skipped.append({"filename": source_path.name, "reason": str(exc)[:200]})
            continue
        if file_type not in {"pdf", "markdown"}:
            skipped.append({"filename": source_path.name, "reason": "unsupported_for_reading"})
            continue
        candidates.append(
            {
                "entry_id": f"folder-{index}",
                "file_id": "",
                "title": source_path.stem,
                "filename": source_path.name,
                "relative_path": str(source_path.relative_to(input_folder)),
                "extension": source_path.suffix.lower(),
                "size_bytes": size_bytes,
                "md5": md5_hash,
                "preview": _extract_preview(source_path, file_type, max_chars=1400),
            }
        )

    md5_values = [item["md5"] for item in candidates]
    existing_files = []
    if md5_values:
        existing_files = (
            await db.execute(
                select(File).where(
                    File.owner_user_id == user.id,
                    File.md5.in_(md5_values),
                )
            )
        ).scalars().all()
    file_by_md5 = {file_record.md5: file_record for file_record in existing_files}
    file_ids = [file_record.id for file_record in existing_files]
    entries_by_file_id: dict[str, BibEntry] = {}
    if file_ids:
        existing_entries = (
            await db.execute(
                select(BibEntry).where(
                    BibEntry.owner_user_id == user.id,
                    BibEntry.source_file_id.in_(file_ids),
                )
            )
        ).scalars().all()
        entries_by_file_id = {
            str(entry.source_file_id): entry
            for entry in existing_entries
            if entry.source_file_id
        }
    library_entries = (
        await db.execute(select(BibEntry).where(BibEntry.owner_user_id == user.id))
    ).scalars().all()

    all_topic = _is_all_topic(topic)
    relevance_rows = [] if all_topic else _classify_relevance(api_key, topic, candidates)
    relevance_by_id = {str(row.get("entry_id")): row for row in relevance_rows if isinstance(row, dict)}
    rows = []
    for item in candidates:
        row = relevance_by_id.get(item["entry_id"]) or {}
        confidence = 1.0 if all_topic else float(row.get("confidence") or 0)
        relevant = all_topic or (bool(row.get("relevant")) and confidence >= float(confidence_threshold))
        exact_file = file_by_md5.get(item["md5"])
        exact_entry = entries_by_file_id.get(exact_file.id) if exact_file else None
        best_entry = None
        best_score = 0.0
        if exact_entry is None:
            for entry in library_entries:
                score = title_match_score(item["title"], entry.title or "")
                if score > best_score:
                    best_score = score
                    best_entry = entry

        if exact_entry is not None:
            library_match = {
                "status": "in_library",
                "method": "file_md5",
                "score": 1.0,
                "entry_id": exact_entry.id,
                "library_title": exact_entry.title,
                "file_id": exact_file.id,
                "reading_status": exact_entry.reading_status,
            }
        elif exact_file is not None:
            library_match = {
                "status": "file_exists_no_bib_entry",
                "method": "file_md5",
                "score": 1.0,
                "entry_id": None,
                "library_title": None,
                "file_id": exact_file.id,
                "reading_status": None,
            }
        elif best_entry is not None and best_score >= 0.72:
            library_match = {
                "status": "possible_match",
                "method": "title_similarity",
                "score": round(best_score, 3),
                "entry_id": best_entry.id,
                "library_title": best_entry.title,
                "file_id": best_entry.source_file_id,
                "reading_status": best_entry.reading_status,
            }
        else:
            library_match = {
                "status": "not_in_library",
                "method": "md5_and_title",
                "score": round(best_score, 3),
                "entry_id": None,
                "library_title": best_entry.title if best_entry else None,
                "file_id": None,
                "reading_status": None,
            }
        rows.append(
            {
                "title": item["title"],
                "filename": item["filename"],
                "relative_path": item["relative_path"],
                "extension": item["extension"],
                "size_bytes": item["size_bytes"],
                "relevant": relevant,
                "confidence": confidence,
                "library_match": library_match,
                "reason": "topic=*，全部列出。" if all_topic else (row.get("reason") or ""),
            }
        )

    return {
        "input_folder_path": input_folder_path,
        "topic": topic,
        "scanned": len(files),
        "count": len(rows),
        "relevant_count": sum(1 for row in rows if row["relevant"]),
        "library_counts": {
            "in_library": sum(1 for row in rows if row["library_match"]["status"] == "in_library"),
            "possible_match": sum(1 for row in rows if row["library_match"]["status"] == "possible_match"),
            "not_in_library": sum(1 for row in rows if row["library_match"]["status"] == "not_in_library"),
            "file_exists_no_bib_entry": sum(1 for row in rows if row["library_match"]["status"] == "file_exists_no_bib_entry"),
        },
        "papers": rows,
        "skipped": skipped,
        "note": "这是只读清单；未导入文件，也未启动精读任务。",
    }


async def tool_import_folder_and_start_reading(
    db: AsyncSession,
    user: User,
    *,
    api_key: str,
    topic: str,
    mode: str,
    recursive: bool = False,
    max_files: int = 30,
    confidence_threshold: float = 0.55,
    conflict_resolution: str = "skip",
    analysis_dims: list[str] | None = None,
    custom_question: str | None = None,
    extraction_method: str = "full",
) -> dict[str, Any]:
    if mode not in {"quant", "qual", "long"}:
        return {"error": "mode_must_be_quant_qual_or_long"}
    prefs = await get_agent_preferences(db, user)
    input_folder_path = prefs.get("input_folder_path") or ""
    if not input_folder_path:
        return {"error": "input_folder_not_configured", "hint": "请先在设置里保存 input 文件夹白名单路径。"}
    input_folder = Path(input_folder_path)
    if not input_folder.exists() or not input_folder.is_dir():
        return {"error": "input_folder_missing", "path": input_folder_path}

    files = _collect_folder_files(input_folder, recursive, max_files)
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for source_path in files:
        try:
            result = await _import_source_file(db, user, source_path)
        except Exception as exc:
            skipped.append({"path": str(source_path), "status": "error", "reason": str(exc)[:300]})
            continue
        if result.get("file_id") and result.get("entry_id"):
            imported.append(result)
        else:
            skipped.append(result)

    all_topic = _is_all_topic(topic)
    relevance_rows = [] if all_topic else _classify_relevance(api_key, topic, imported)
    relevance_by_id = {str(row.get("entry_id")): row for row in relevance_rows if isinstance(row, dict)}
    selected = []
    rejected = []
    for item in imported:
        row = relevance_by_id.get(item["entry_id"]) or {}
        confidence = 1.0 if all_topic else float(row.get("confidence") or 0)
        relevant = all_topic or (bool(row.get("relevant")) and confidence >= float(confidence_threshold))
        payload = {
            "file_id": item["file_id"],
            "entry_id": item["entry_id"],
            "title": item["title"],
            "filename": item["filename"],
            "confidence": confidence,
            "reason": "topic=*，跳过主题筛选，全部纳入。" if all_topic else (row.get("reason") or ""),
        }
        if relevant:
            selected.append(payload)
        else:
            rejected.append(payload)

    batch = None
    if selected:
        batch = await tool_start_batch_reading(
            db,
            user,
            api_key=api_key,
            mode=mode,
            file_ids=[item["file_id"] for item in selected],
            analysis_dims=analysis_dims or [],
            custom_question=custom_question,
            extraction_method=extraction_method,
            conflict_resolution=conflict_resolution,
        )

    return {
        "input_folder_path": input_folder_path,
        "topic": topic,
        "mode": mode,
        "scanned": len(files),
        "imported_or_seen": len(imported),
        "skipped": skipped,
        "selected_count": len(selected),
        "selected": selected,
        "rejected": rejected,
        "batch": batch,
    }


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_library",
            "description": "Search the user's bibliography library by title, abstract, journal, keyword, or tag.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "reading_status": {"type": "string", "enum": ["", "none", "has_pdf", "reading", "read"]},
                    "limit": {"type": "integer", "minimum": 1},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entry_detail",
            "description": "Get metadata, source file id, and recent workflow timeline for a bibliography entry.",
            "parameters": {
                "type": "object",
                "properties": {"entry_id": {"type": "string"}},
                "required": ["entry_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reading_context",
            "description": "Fetch structured deep-reading sections for selected entries so the assistant can compare or synthesize them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entry_ids": {"type": "array", "items": {"type": "string"}},
                    "mode": {"type": "string", "enum": ["", "long", "quant", "qual"]},
                    "max_chars_per_item": {"type": "integer", "minimum": 300, "maximum": 8000},
                },
                "required": ["entry_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_reading",
            "description": "Start a long, quantitative 7-step, or qualitative 4-step reading job for one PDF/Markdown file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["long", "quant", "qual"]},
                    "file_id": {"type": "string"},
                    "entry_id": {"type": "string"},
                    "analysis_dims": {"type": "array", "items": {"type": "string"}},
                    "custom_question": {"type": "string"},
                    "extraction_method": {"type": "string", "enum": ["full", "smart", "first_pages"]},
                    "conflict_resolution": {"type": "string", "enum": ["check", "overwrite", "new", "incremental", "skip"]},
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_batch_reading",
            "description": "Start reading jobs for multiple file ids.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["long", "quant", "qual"]},
                    "file_ids": {"type": "array", "items": {"type": "string"}},
                    "analysis_dims": {"type": "array", "items": {"type": "string"}},
                    "custom_question": {"type": "string"},
                    "extraction_method": {"type": "string", "enum": ["full", "smart", "first_pages"]},
                    "conflict_resolution": {"type": "string", "enum": ["check", "overwrite", "new", "incremental", "skip"]},
                },
                "required": ["mode", "file_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_input_folder",
            "description": (
                "Read-only scan of the configured input folder whitelist and compare it with the user's library. "
                "Use this when the user asks to see, list, inspect, or tabulate papers. "
                "This never imports files and never starts reading jobs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "recursive": {"type": "boolean"},
                    "max_files": {"type": "integer", "minimum": 1, "maximum": 100},
                    "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_folder_and_start_reading",
            "description": (
                "Scan the configured input folder whitelist, import PDF/Markdown files, "
                "select papers related to a topic, and start batch reading jobs. "
                "Use only when the user explicitly asks to start/run/batch read/analyze."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "mode": {"type": "string", "enum": ["quant", "qual", "long"]},
                    "recursive": {"type": "boolean"},
                    "max_files": {"type": "integer", "minimum": 1, "maximum": 100},
                    "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                    "conflict_resolution": {"type": "string", "enum": ["check", "overwrite", "new", "incremental", "skip"]},
                    "analysis_dims": {"type": "array", "items": {"type": "string"}},
                    "custom_question": {"type": "string"},
                    "extraction_method": {"type": "string", "enum": ["full", "smart", "first_pages"]},
                },
                "required": ["topic", "mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_status",
            "description": "Get status and artifact links for a reading or synthesis job.",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
            },
        },
    },
]


async def execute_tool(
    name: str,
    args: dict[str, Any],
    *,
    db: AsyncSession,
    user: User,
    api_key: str,
    session: AgentSession,
) -> dict[str, Any]:
    if name == "search_library":
        return await tool_search_library(db, user, **args)
    if name == "get_entry_detail":
        return await tool_get_entry_detail(db, user, **args)
    if name == "get_reading_context":
        return await tool_get_reading_context(db, user, **args)
    if name == "start_reading":
        preview = {"action": "start_reading", "arguments": args, "note": "确认后才会启动单篇精读任务。"}
        return await _create_proposal(db, user, session, action_type=name, arguments=args, preview=preview)
    if name == "start_batch_reading":
        preview = {
            "action": "start_batch_reading",
            "mode": args.get("mode"),
            "file_count": len(args.get("file_ids") or []),
            "file_ids": args.get("file_ids") or [],
            "note": "确认后才会启动批量精读任务。",
        }
        return await _create_proposal(db, user, session, action_type=name, arguments=args, preview=preview)
    if name == "scan_input_folder":
        return await tool_scan_input_folder(db, user, api_key=api_key, **args)
    if name == "import_folder_and_start_reading":
        preview = await tool_scan_input_folder(
            db,
            user,
            api_key=api_key,
            topic=args.get("topic", "*"),
            recursive=bool(args.get("recursive", False)),
            max_files=int(args.get("max_files") or 50),
            confidence_threshold=float(args.get("confidence_threshold") or 0.55),
        )
        preview = {
            **preview,
            "action": "import_folder_and_start_reading",
            "mode": args.get("mode"),
            "note": "这是执行提案预览；确认后才会导入文件并启动精读任务。",
        }
        return await _create_proposal(db, user, session, action_type=name, arguments=args, preview=preview)
    if name == "get_job_status":
        return await tool_get_job_status(db, user, **args)
    return {"error": f"unknown_tool:{name}"}


def build_messages(req: AgentChatRequest) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "你是 Deep Reading Agent 的文献工作台助手。你可以调用工具检索文献库、查看精读结果、"
                "启动精读任务、查询任务状态，并基于工具返回的真实数据做对比和综述。"
                "当用户要求扫描 input 文件夹、某个已配置文件夹或文件夹里与主题相关的文献时，"
                "使用 import_folder_and_start_reading；不要要求用户提供任意路径。"
                "如果主题是 *，含义是全部文献，不要解释成某个研究主题。"
                "涉及文献列表、精读状态、任务进度、综述依据时必须先调用工具，不要编造。"
                "启动长耗时任务前，如果用户已经明确要求执行，可以直接调用工具；如果缺少 file_id/entry_id/"
                "精读模式等必要信息，先通过工具查找，仍不足再说明需要用户补充。"
                "回答要简洁，列出已调用的任务 id、文献 id、下一步操作。"
            ),
        }
    ]
    messages.append(
        {
            "role": "system",
            "content": (
                "补充硬规则：严格区分查看和执行。用户说“看看、列出、扫描、有哪些、列个表、筛出相关文献”时，"
                "只能调用 scan_input_folder，不能导入文件，不能启动精读。只有用户明确说“启动、开始、执行、"
                "精读、批量精读、用七步法、用四步法、长文本精读”时，才允许调用会启动任务的工具。"
                "主题为 * 表示全部文献。"
            ),
        }
    )
    for turn in req.history[-8:]:
        messages.append({"role": turn.role, "content": turn.content})
    messages.append({"role": "user", "content": req.message})
    return messages


@router.post("/chat")
async def agent_chat(
    req: AgentChatRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        api_key = validate_deepseek_key(req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
    )

    async def _stream():
        try:
            session = await _ensure_session(db, user, req)
            yield sse_event(
                "session",
                {
                    "session_id": session.id,
                    "title": session.title,
                    "last_state": _json_loads(session.last_state_json, {}) or {},
                },
            )
            await _save_agent_message(db, user, session, role="user", event_type="message", content=req.message)
            await db.commit()

            messages = build_messages(req)
            state = _json_loads(session.last_state_json, {}) or {}
            if state:
                messages.insert(
                    1,
                    {
                        "role": "system",
                        "content": "当前持久会话可引用状态：" + json.dumps(state, ensure_ascii=False)[:6000],
                    },
                )

            for _ in range(MAX_TOOL_ROUNDS):
                response = client.chat.completions.create(
                    model=MODEL,
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                    temperature=0.2,
                    max_tokens=4000,
                )
                message = response.choices[0].message
                tool_calls = message.tool_calls or []
                messages.append(message.model_dump(exclude_none=True))
                if not tool_calls:
                    content = message.content or ""
                    await _save_agent_message(db, user, session, role="assistant", event_type="message", content=content)
                    await db.commit()
                    yield sse_event("answer", {"content": content})
                    yield sse_event("done", {})
                    return

                for tool_call in tool_calls:
                    name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    yield sse_event("tool_call", {"name": name, "arguments": args})
                    await _save_agent_message(
                        db,
                        user,
                        session,
                        role="assistant",
                        event_type="tool_call",
                        tool_name=name,
                        payload=args,
                    )
                    result = await execute_tool(name, args, db=db, user=user, api_key=api_key, session=session)
                    await _save_agent_message(
                        db,
                        user,
                        session,
                        role="tool",
                        event_type="tool_result",
                        tool_name=name,
                        payload=result,
                    )
                    if name == "scan_input_folder":
                        await _update_session_state(db, session, key="last_scan", value=result)
                    if isinstance(result, dict) and result.get("proposal_id"):
                        yield sse_event("proposal", result)
                    await db.commit()
                    yield sse_event("tool_result", {"name": name, "result": result})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )

            yield sse_event(
                "answer",
                {"content": "工具调用轮次已达上限。我已经把可获得的信息列在上方，请缩小范围后继续。"},
            )
            yield sse_event("done", {})
        except Exception as exc:
            yield sse_event("error", {"message": str(exc)})

    return StreamingResponse(_stream(), media_type="text/event-stream")
