"""Tool-calling literature assistant router."""
from __future__ import annotations

import asyncio
import json
import hashlib
import logging
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

import httpx
from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, UploadFile
try:
    from openai import APIConnectionError, APIStatusError, APITimeoutError
except ImportError:  # pragma: no cover - compatibility with older SDKs
    APIConnectionError = APIStatusError = APITimeoutError = ()  # type: ignore[assignment]
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
    from backend.services.agent_external_retrieval import tool_lookup_english_fulltext, tool_search_cnki
    from backend.services.research_agent_runtime import (
        append_working_note,
        apply_execution_result_to_state,
        build_stop_summary,
        build_runtime_system_prompts,
        build_task_frame,
        enforce_tool_policy,
        normalize_tool_args,
        resolve_context_refs,
        summarize_state_for_ui,
        update_state_after_tool,
    )
    from backend.services.reading_candidate_analysis import analyze_reading_candidates, filter_analysis_cache
    from backend.services.agent_tool_registry import TOOL_SCHEMAS as REGISTERED_TOOL_SCHEMAS, list_tool_capabilities
    from backend.services.research_retrieval import (
        ResearchQuery,
        get_evidence_pack,
        get_source_windows,
        research_search,
    )
    from backend.utils.api_key import validate_deepseek_key
    from backend.services.agent_errors import AgentErrorCode, RuntimeNoticeCode, make_agent_error_payload
    from backend.utils.llm_provider import (
        create_openai_client,
        describe_llm_provider,
        model_for_api_key,
        probe_llm_provider,
        resolve_llm_provider,
    )
except ModuleNotFoundError:  # Support the backend/ working directory used by local checks.
    from routers import reading
    from services.agent_external_retrieval import tool_lookup_english_fulltext, tool_search_cnki
    from services.research_agent_runtime import (
        append_working_note,
        apply_execution_result_to_state,
        build_stop_summary,
        build_runtime_system_prompts,
        build_task_frame,
        enforce_tool_policy,
        normalize_tool_args,
        resolve_context_refs,
        summarize_state_for_ui,
        update_state_after_tool,
    )
    from services.reading_candidate_analysis import analyze_reading_candidates, filter_analysis_cache
    from services.agent_tool_registry import TOOL_SCHEMAS as REGISTERED_TOOL_SCHEMAS, list_tool_capabilities
    from services.research_retrieval import (
        ResearchQuery,
        get_evidence_pack,
        get_source_windows,
        research_search,
    )
    from utils.api_key import validate_deepseek_key
    from utils.llm_provider import (
        create_openai_client,
        describe_llm_provider,
        model_for_api_key,
        probe_llm_provider,
        resolve_llm_provider,
    )
    from services.agent_errors import AgentErrorCode, RuntimeNoticeCode, make_agent_error_payload
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
    UploadBatch,
    User,
    UserSettings,
)
from db.utils import title_match_score
from routers.upload import ALLOWED_EXTENSIONS, bind_uploaded_file_to_existing_bib, detect_file_type
from upload_storage import build_storage_path, get_user_upload_dir, resolve_storage_path

router = APIRouter()

MODEL = "deepseek-v4-flash"
MAX_TOOL_ROUNDS = 8
AGENT_INBOX_EXTENSIONS = {".pdf", ".md", ".markdown"}
AGENT_INBOX_MAX_FILES = 200


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


class AgentProviderCheckRequest(BaseModel):
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


def _as_error_message(detail: Any) -> str:
    if isinstance(detail, dict):
        for key in ("message", "detail", "error"):
            value = detail.get(key)
            if value:
                return str(value)
        return json.dumps(detail, ensure_ascii=False)
    return str(detail or "")


def _structured_agent_error(
    *,
    code: AgentErrorCode,
    message: str,
    stage: str,
    retryable: bool,
    status_code: int | None = None,
    provider: str | None = None,
    tool: str | None = None,
    details: Any = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    return make_agent_error_payload(
        code=code,
        message=message,
        stage=stage,
        retryable=retryable,
        status_code=status_code,
        provider=provider,
        tool=tool,
        details=details,
        recommendations=recommendations,
    )


def classify_agent_exception(
    exc: Exception,
    *,
    stage: str,
    provider: str | None = None,
    tool: str | None = None,
) -> dict[str, Any]:
    exc_name = exc.__class__.__name__

    if isinstance(exc, HTTPException):
        status_code = int(exc.status_code)
        message = _as_error_message(exc.detail) or f"HTTP {status_code}"
        if status_code == 400 and "key" in message.lower():
            return _structured_agent_error(
                code=AgentErrorCode.INVALID_API_KEY,
                message=message,
                stage=stage,
                retryable=False,
                status_code=status_code,
                provider=provider,
                tool=tool,
                details=exc.detail,
                recommendations=[
                    "检查右上角 API Key 是否完整、未过期，且不要包含占位符。",
                    "如果使用 provider 前缀，请确认 Key 类型和前缀匹配。",
                ],
            )
        if status_code in {401, 403}:
            return _structured_agent_error(
                code=AgentErrorCode.PERMISSION_DENIED,
                message=message,
                stage=stage,
                retryable=False,
                status_code=status_code,
                provider=provider,
                tool=tool,
                details=exc.detail,
                recommendations=["检查当前账号权限、会话状态或相关资源是否属于当前用户。"],
            )
        if status_code == 404:
            return _structured_agent_error(
                code=AgentErrorCode.RESOURCE_NOT_FOUND,
                message=message,
                stage=stage,
                retryable=False,
                status_code=status_code,
                provider=provider,
                tool=tool,
                details=exc.detail,
                recommendations=["确认引用的 session、proposal、job 或文献对象仍然存在。"],
            )
        return _structured_agent_error(
            code=AgentErrorCode.HTTP_ERROR,
            message=message,
            stage=stage,
            retryable=status_code >= 500,
            status_code=status_code,
            provider=provider,
            tool=tool,
            details=exc.detail,
            recommendations=["如问题持续存在，请刷新后重试，或缩小当前操作范围。"],
        )

    if isinstance(exc, ValueError) and "key" in str(exc).lower():
        return _structured_agent_error(
            code=AgentErrorCode.INVALID_API_KEY,
            message=str(exc),
            stage=stage,
            retryable=False,
            provider=provider,
            tool=tool,
            recommendations=[
                "检查 API Key 是否完整、真实且未过期。",
                "如果是 MiMo Token Plan，请确认是否使用 tp- 开头的 Key。",
            ],
        )

    if isinstance(exc, httpx.TimeoutException) or exc_name in {"APITimeoutError", "ReadTimeout", "ConnectTimeout"}:
        return _structured_agent_error(
            code=AgentErrorCode.LLM_TIMEOUT,
            message="上游模型响应超时，请稍后重试，或缩小问题范围后再试。",
            stage=stage,
            retryable=True,
            provider=provider,
            tool=tool,
            details=str(exc),
            recommendations=["缩小问题范围后重试。", "如是长任务，可改为先检索再逐步总结。"],
        )

    if isinstance(exc, httpx.NetworkError) or isinstance(exc, APIConnectionError) or exc_name == "APIConnectionError":
        return _structured_agent_error(
            code=AgentErrorCode.LLM_CONNECTION_ERROR,
            message="连接上游模型服务失败，请检查网络或稍后重试。",
            stage=stage,
            retryable=True,
            provider=provider,
            tool=tool,
            details=str(exc),
            recommendations=["检查当前网络连接。", "稍后重试，或确认上游服务是否可用。"],
        )

    status_code = getattr(exc, "status_code", None)
    if isinstance(exc, APIStatusError) and getattr(exc, "status_code", None) is not None:
        status_code = int(exc.status_code)
    if exc_name in {"AuthenticationError"} or status_code == 401:
        return _structured_agent_error(
            code=AgentErrorCode.LLM_AUTH_ERROR,
            message="上游模型认证失败，请检查 API Key 是否有效或 provider 是否匹配。",
            stage=stage,
            retryable=False,
            status_code=int(status_code) if status_code is not None else None,
            provider=provider,
            tool=tool,
            details=str(exc),
            recommendations=["重新检查 API Key。", "确认当前 provider 和 Key 类型匹配。"],
        )
    if exc_name in {"RateLimitError"} or status_code == 429:
        return _structured_agent_error(
            code=AgentErrorCode.LLM_RATE_LIMITED,
            message="上游模型触发限流，请稍后再试。",
            stage=stage,
            retryable=True,
            status_code=int(status_code) if status_code is not None else None,
            provider=provider,
            tool=tool,
            details=str(exc),
            recommendations=["稍等一会后重试。", "缩小问题范围，减少连续高频请求。"],
        )
    if exc_name in {"BadRequestError", "UnprocessableEntityError"} or status_code in {400, 422}:
        return _structured_agent_error(
            code=AgentErrorCode.LLM_BAD_REQUEST,
            message="提交给上游模型的请求不合法，请调整当前问题或参数后重试。",
            stage=stage,
            retryable=False,
            status_code=int(status_code) if status_code is not None else None,
            provider=provider,
            tool=tool,
            details=str(exc),
            recommendations=["缩短输入内容。", "避免一次性请求过多文献或过长上下文。"],
        )
    if exc_name in {"InternalServerError"} or (status_code is not None and int(status_code) >= 500):
        return _structured_agent_error(
            code=AgentErrorCode.LLM_UPSTREAM_ERROR,
            message="上游模型服务暂时异常，请稍后重试。",
            stage=stage,
            retryable=True,
            status_code=int(status_code),
            provider=provider,
            tool=tool,
            details=str(exc),
            recommendations=["稍后重试。", "如果问题持续出现，可先缩小任务范围。"],
        )

    if stage == "tool_execution":
        return _structured_agent_error(
            code=AgentErrorCode.TOOL_EXECUTION_ERROR,
            message=f"工具 {tool or ''} 执行失败。".strip(),
            stage=stage,
            retryable=True,
            provider=provider,
            tool=tool,
            details=str(exc),
            recommendations=["检查相关输入对象是否存在。", "必要时改为先检索再执行。"],
        )

    return _structured_agent_error(
        code=AgentErrorCode.AGENT_RUNTIME_ERROR,
        message=str(exc) or "AI 助手执行失败。",
        stage=stage,
        retryable=False,
        provider=provider,
        tool=tool,
        details=str(exc),
        recommendations=["请刷新后重试。", "如果问题持续存在，请反馈当前问题和上下文。"],
    )


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


async def _replace_session_state(
    db: AsyncSession,
    session: AgentSession,
    *,
    state: dict[str, Any],
) -> None:
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
    inbox_batch_id = str(agent_prefs.get("input_batch_id") or "")
    inbox_batch = None
    if inbox_batch_id:
        batch = await db.get(UploadBatch, inbox_batch_id)
        if batch and batch.owner_user_id == user.id:
            inbox_batch = {
                "batch_id": batch.id,
                "total_files": batch.total_files,
                "succeeded": batch.succeeded,
                "failed": batch.failed,
                "status": batch.status,
                "note": batch.note,
                "created_at": _dt(batch.created_at),
            }
    return {
        "input_folder_path": str(agent_prefs.get("input_folder_path") or ""),
        "input_batch_id": inbox_batch_id,
        "input_file_ids": [
            str(file_id)
            for file_id in agent_prefs.get("input_file_ids", [])
            if file_id
        ] if isinstance(agent_prefs.get("input_file_ids"), list) else [],
        "inbox_batch": inbox_batch,
        "inbox_upload_summary": agent_prefs.get("inbox_upload_summary") if isinstance(agent_prefs.get("inbox_upload_summary"), dict) else None,
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


def _inbox_error_message(code: str) -> str:
    mapping = {
        "missing_filename": "文件名缺失",
        "unsupported_extension": "文件扩展名不受支持",
        "empty_file": "空文件",
        "unsupported_for_agent": "AI 助手仅支持 PDF/Markdown",
        "input_batch_missing": "上传批次不存在",
        "input_inbox_not_configured": "尚未上传 AI 助手文件夹",
        "input_folder_missing": "源文件夹不存在",
        "unsupported_for_reading": "文件类型不支持扫描",
    }
    return mapping.get(code, code or "unknown_error")


def _summarize_upload_results(batch: UploadBatch, results: list[dict[str, Any]]) -> dict[str, Any]:
    error_counts: dict[str, int] = {}
    failed_examples: list[dict[str, str]] = []
    imported_count = 0
    deduplicated_count = 0
    matched_count = 0
    unmatched_count = 0

    for item in results:
        if item.get("success"):
            if item.get("deduplicated"):
                deduplicated_count += 1
            else:
                imported_count += 1
            if item.get("matched_bib_entry_id"):
                matched_count += 1
            else:
                unmatched_count += 1
            continue

        error_code = str(item.get("error") or "unknown_error")
        error_counts[error_code] = int(error_counts.get(error_code) or 0) + 1
        if len(failed_examples) < 5:
            failed_examples.append(
                {
                    "filename": str(item.get("filename") or ""),
                    "error": error_code,
                    "message": _inbox_error_message(error_code),
                }
            )

    recommendations: list[str] = []
    if batch.failed:
        recommendations.append("先处理失败文件，再让 AI 助手扫描这批文件。")
    if unmatched_count:
        recommendations.append("部分文件尚未绑定到文献库，后续扫描后可能需要人工确认匹配关系。")
    if deduplicated_count:
        recommendations.append("有重复文件已自动复用既有上传记录，无需重复导入。")

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "total_files": batch.total_files,
        "succeeded": batch.succeeded,
        "failed": batch.failed,
        "imported_count": imported_count,
        "deduplicated_count": deduplicated_count,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "error_counts": error_counts,
        "failed_examples": failed_examples,
        "recommendations": recommendations,
        "created_at": _dt(batch.created_at),
    }


def _summarize_scan_result(
    *,
    source: str,
    topic: str,
    scanned: int,
    rows: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    input_batch_id: str,
) -> dict[str, Any]:
    skipped_reasons: dict[str, int] = {}
    skipped_examples: list[dict[str, str]] = []
    for item in skipped:
        reason = str(item.get("reason") or "unknown_error")
        skipped_reasons[reason] = int(skipped_reasons.get(reason) or 0) + 1
        if len(skipped_examples) < 5:
            skipped_examples.append(
                {
                    "filename": str(item.get("filename") or ""),
                    "reason": reason,
                    "message": _inbox_error_message(reason),
                }
            )

    relevant_count = sum(1 for row in rows if row.get("relevant"))
    in_library = sum(1 for row in rows if (row.get("library_match") or {}).get("status") == "in_library")
    possible_match = sum(1 for row in rows if (row.get("library_match") or {}).get("status") == "possible_match")
    not_in_library = sum(1 for row in rows if (row.get("library_match") or {}).get("status") == "not_in_library")
    file_exists_no_bib = sum(
        1 for row in rows if (row.get("library_match") or {}).get("status") == "file_exists_no_bib_entry"
    )
    recommendations: list[str] = []
    if relevant_count == 0 and rows:
        recommendations.append("当前主题下没有筛出相关文献，可以改成更宽泛的主题再试。")
    if not_in_library or file_exists_no_bib:
        recommendations.append("部分文件还未形成稳定题录映射，导入或扫描后可能需要人工确认。")
    if skipped:
        recommendations.append("有文件被跳过，建议先检查失败原因再继续扫描或导入。")

    return {
        "source": source,
        "topic": topic,
        "batch_id": input_batch_id or None,
        "scanned": scanned,
        "candidate_count": len(rows),
        "relevant_count": relevant_count,
        "library_counts": {
            "in_library": in_library,
            "possible_match": possible_match,
            "not_in_library": not_in_library,
            "file_exists_no_bib_entry": file_exists_no_bib,
        },
        "skipped_count": len(skipped),
        "skipped_reasons": skipped_reasons,
        "skipped_examples": skipped_examples,
        "recommendations": recommendations,
    }


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


@router.post("/provider-check")
async def check_agent_provider(
    req: AgentProviderCheckRequest,
    user: User = Depends(current_user),
):
    del user
    try:
        api_key = validate_deepseek_key(req.api_key, source="AI 助手设置")
        provider_info = describe_llm_provider(api_key, source="AI 助手设置", requested_model=MODEL)
        probe = probe_llm_provider(
            api_key,
            source="AI 助手设置",
            requested_model=MODEL,
            timeout=httpx.Timeout(connect=10.0, read=25.0, write=10.0, pool=10.0),
        )
        return {
            "ok": True,
            "provider": probe["provider"],
            "provider_label": probe["provider_label"],
            "base_url": probe["base_url"],
            "model": probe["model"],
            "key_prefix": probe["key_prefix"],
            "explicit_provider": probe["explicit_provider"],
            "latency_ms": probe["latency_ms"],
            "response_preview": probe.get("response_preview") or "",
            "checked_at": _dt(utcnow_naive()),
        }
    except Exception as exc:
        payload = classify_agent_exception(exc, stage="provider_probe")
        raise HTTPException(
            status_code=int(payload.get("status_code") or (400 if payload.get("retryable") is False else 502)),
            detail={
                **payload,
                **(
                    provider_info
                    if "provider_info" in locals() and isinstance(provider_info, dict)
                    else {}
                ),
            },
        )


@router.get("/tool-capabilities")
async def get_agent_tool_capabilities(
    user: User = Depends(current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return {"tools": list_tool_capabilities()}


async def _persist_inbox_upload(
    db: AsyncSession,
    user: User,
    upload: UploadFile,
    batch_id: str,
) -> dict[str, Any]:
    """Persist an uploaded file to the inbox with structured logging.

    Returns a dict with success status, file_id, and any matched bib entry.
    """
    original_name = (upload.filename or "").strip().replace("\\", "/")
    if not original_name:
        logger.warning("[inbox_upload] missing_filename: user_id=%s, batch_id=%s", user.id, batch_id)
        return {"success": False, "filename": "", "error": "missing_filename"}

    file_ext = Path(original_name).suffix.lower()
    if file_ext not in AGENT_INBOX_EXTENSIONS:
        logger.warning(
            "[inbox_upload] unsupported_extension: user_id=%s, batch_id=%s, filename=%s, ext=%s",
            user.id, batch_id, original_name, file_ext
        )
        return {"success": False, "filename": original_name, "error": "unsupported_extension"}

    logger.info("[inbox_upload] started: user_id=%s, batch_id=%s, filename=%s", user.id, batch_id, original_name)

    user_dir = get_user_upload_dir(user.id)
    temp_path = user_dir / f".{uuid.uuid4()}.agent-uploading"
    final_path: Path | None = None
    file_id: str | None = None

    try:
        hasher = hashlib.md5()
        size_bytes = 0
        sample = b""
        with temp_path.open("wb") as buffer:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                if not sample:
                    sample = chunk[:4096]
                hasher.update(chunk)
                buffer.write(chunk)
                size_bytes += len(chunk)

        logger.debug(
            "[inbox_upload] file_read: user_id=%s, batch_id=%s, filename=%s, size_bytes=%d",
            user.id, batch_id, original_name, size_bytes
        )

        if size_bytes <= 0:
            logger.warning(
                "[inbox_upload] empty_file: user_id=%s, batch_id=%s, filename=%s",
                user.id, batch_id, original_name
            )
            return {"success": False, "filename": original_name, "error": "empty_file"}

        file_type = detect_file_type(original_name, sample)
        if file_type not in {"pdf", "markdown"}:
            logger.warning(
                "[inbox_upload] unsupported_type: user_id=%s, batch_id=%s, filename=%s, detected_type=%s",
                user.id, batch_id, original_name, file_type
            )
            return {"success": False, "filename": original_name, "error": "unsupported_for_agent"}

        md5_hash = hasher.hexdigest()
        logger.debug(
            "[inbox_upload] hash_computed: user_id=%s, batch_id=%s, filename=%s, md5=%s",
            user.id, batch_id, original_name, md5_hash
        )

        existing = (
            await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
        ).scalar_one_or_none()

        if existing is not None:
            matched_bib = await bind_uploaded_file_to_existing_bib(db, user, existing)
            await db.flush()
            logger.info(
                "[inbox_upload] deduplicated: user_id=%s, batch_id=%s, filename=%s, existing_file_id=%s, matched_bib=%s",
                user.id, batch_id, original_name, existing.id, matched_bib.id if matched_bib else None
            )
            return {
                "success": True,
                "deduplicated": True,
                "file_id": existing.id,
                "filename": existing.original_name,
                "matched_bib_entry_id": matched_bib.id if matched_bib else None,
            }

        file_id = str(uuid.uuid4())
        final_path, storage_path = build_storage_path(user.id, file_id, file_ext)
        shutil.move(str(temp_path), str(final_path))
        logger.debug(
            "[inbox_upload] file_moved: user_id=%s, batch_id=%s, filename=%s, file_id=%s, storage_path=%s",
            user.id, batch_id, original_name, file_id, storage_path
        )

        record = File(
            id=file_id,
            owner_user_id=user.id,
            original_name=original_name,
            file_type=file_type,
            storage_path=storage_path,
            size_bytes=size_bytes,
            md5=md5_hash,
            batch_id=batch_id,
            expires_at=reading.compute_expires_at(user),
        )
        db.add(record)
        matched_bib = await bind_uploaded_file_to_existing_bib(db, user, record)
        await db.flush()
        logger.info(
            "[inbox_upload] success: user_id=%s, batch_id=%s, filename=%s, file_id=%s, matched_bib=%s",
            user.id, batch_id, original_name, file_id, matched_bib.id if matched_bib else None
        )
        return {
            "success": True,
            "deduplicated": False,
            "file_id": record.id,
            "filename": record.original_name,
            "matched_bib_entry_id": matched_bib.id if matched_bib else None,
        }
    except Exception as exc:
        logger.exception(
            "[inbox_upload] exception: user_id=%s, batch_id=%s, filename=%s, file_id=%s, exc_type=%s, exc_msg=%s",
            user.id, batch_id, original_name, file_id, type(exc).__name__, str(exc)[:200]
        )
        raise
    finally:
        if temp_path.exists():
            temp_path.unlink()
        await upload.close()


@router.post("/inbox/upload-folder")
async def upload_agent_inbox_folder(
    files: list[UploadFile] = FastAPIFile(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > AGENT_INBOX_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多上传 {AGENT_INBOX_MAX_FILES} 个 PDF/Markdown 文件。")

    batch = UploadBatch(
        id=str(uuid.uuid4()),
        owner_user_id=user.id,
        source_type="folder",
        total_files=len(files),
        succeeded=0,
        failed=0,
        status="running",
        note="agent_inbox",
        expires_at=reading.compute_expires_at(user),
    )
    db.add(batch)
    results: list[dict[str, Any]] = []
    for upload in files:
        try:
            result = await _persist_inbox_upload(db, user, upload, batch.id)
        except Exception as exc:
            result = {"success": False, "filename": upload.filename or "", "error": str(exc)[:300]}
        results.append(result)
        if result.get("success"):
            batch.succeeded += 1
        else:
            batch.failed += 1
    batch.status = "success" if batch.failed == 0 else ("partial" if batch.succeeded else "failed")
    upload_summary = _summarize_upload_results(batch, results)
    successful_file_ids = [
        str(result["file_id"])
        for result in results
        if result.get("success") and result.get("file_id")
    ]
    saved = await save_agent_preferences(
        db,
        user,
        {
            "input_batch_id": batch.id,
            "input_file_ids": successful_file_ids,
            "input_folder_path": "",
            "inbox_upload_summary": upload_summary,
        },
    )
    await db.commit()
    return {
        "batch_id": batch.id,
        "total": batch.total_files,
        "succeeded": batch.succeeded,
        "failed": batch.failed,
        "results": results,
        "summary": upload_summary,
        "settings": saved,
    }


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
    state = _json_loads(session.last_state_json, {}) or {}
    state = apply_execution_result_to_state(
        state,
        proposal_id=proposal.id,
        action_type=proposal.action_type,
        proposal_status=proposal.status,
        result=result if isinstance(result, dict) else {},
    )
    await _replace_session_state(db, session, state=state)
    await db.commit()
    return {"proposal": await _proposal_payload(proposal), "result": result, "last_state": summarize_state_for_ui(state)}


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
    state = _json_loads(session.last_state_json, {}) or {}
    pending = state.get("pending_proposal") or {}
    if pending.get("proposal_id") == proposal.id:
        state["pending_proposal"] = None
    await _replace_session_state(db, session, state=state)
    await db.commit()
    return {"proposal": await _proposal_payload(proposal), "last_state": summarize_state_for_ui(state)}


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
    limit = max(1, int(limit or 20))
    normalized_query = "" if str(query or "").strip() == "*" else str(query or "").strip()
    stmt = select(BibEntry, File).outerjoin(File, File.id == BibEntry.source_file_id).where(
        BibEntry.owner_user_id == user.id
    )
    if normalized_query:
        like = f"%{normalized_query}%"
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
    total_count = (
        await db.execute(
            select(func.count())
            .select_from(BibEntry)
            .where(BibEntry.owner_user_id == user.id)
            .where(
                or_(
                    BibEntry.title.ilike(f"%{normalized_query}%"),
                    BibEntry.abstract.ilike(f"%{normalized_query}%"),
                    BibEntry.journal.ilike(f"%{normalized_query}%"),
                    BibEntry.keywords_json.ilike(f"%{normalized_query}%"),
                    BibEntry.user_tags_json.ilike(f"%{normalized_query}%"),
                )
            )
            if normalized_query
            else select(func.count()).select_from(BibEntry).where(BibEntry.owner_user_id == user.id)
        )
    ).scalar_one()
    if reading_status.strip():
        total_count = (
            await db.execute(
                select(func.count())
                .select_from(BibEntry)
                .where(
                    BibEntry.owner_user_id == user.id,
                    BibEntry.reading_status == reading_status.strip(),
                )
                .where(
                    or_(
                        BibEntry.title.ilike(f"%{normalized_query}%"),
                        BibEntry.abstract.ilike(f"%{normalized_query}%"),
                        BibEntry.journal.ilike(f"%{normalized_query}%"),
                        BibEntry.keywords_json.ilike(f"%{normalized_query}%"),
                        BibEntry.user_tags_json.ilike(f"%{normalized_query}%"),
                    )
                )
                if normalized_query
                else select(func.count())
                .select_from(BibEntry)
                .where(
                    BibEntry.owner_user_id == user.id,
                    BibEntry.reading_status == reading_status.strip(),
                )
            )
        ).scalar_one()
    rows = (
        await db.execute(stmt.order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc()).limit(limit))
    ).all()
    return {
        "count": len(rows),
        "total_count": int(total_count or 0),
        "returned_count": len(rows),
        "truncated": bool(total_count and int(total_count) > len(rows)),
        "entries": [_entry_summary(entry, file_record) for entry, file_record in rows],
    }


async def tool_count_library(
    db: AsyncSession,
    user: User,
    *,
    query: str = "",
    reading_status: str = "",
) -> dict[str, Any]:
    normalized_query = "" if str(query or "").strip() == "*" else str(query or "").strip()
    stmt = select(func.count()).select_from(BibEntry).where(BibEntry.owner_user_id == user.id)
    if normalized_query:
        like = f"%{normalized_query}%"
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
    count = (await db.execute(stmt)).scalar_one()
    return {
        "count": int(count or 0),
        "query": normalized_query,
        "reading_status": reading_status.strip() or "",
        "note": "这是数据库总数统计，不含标题枚举。若用户要求列明细，再继续分页检索。",
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
    client = create_openai_client(
        api_key,
        timeout=httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0),
    )
    model = model_for_api_key(api_key, MODEL)
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
        model=model,
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
    input_batch_id = str(prefs.get("input_batch_id") or "")
    input_file_ids = [
        str(file_id)
        for file_id in prefs.get("input_file_ids", [])
        if file_id
    ] if isinstance(prefs.get("input_file_ids"), list) else []
    input_folder_path = str(prefs.get("input_folder_path") or "")
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    source_label = "upload_batch" if input_batch_id else "server_folder"

    if input_batch_id:
        batch = await db.get(UploadBatch, input_batch_id)
        if not batch or batch.owner_user_id != user.id:
            return {"error": "input_batch_missing", "batch_id": input_batch_id}
        if input_file_ids:
            file_records = (
                await db.execute(
                    select(File)
                    .where(
                        File.owner_user_id == user.id,
                        File.id.in_(input_file_ids),
                        File.file_type.in_(["pdf", "markdown"]),
                    )
                    .order_by(File.original_name.asc())
                    .limit(max(1, min(max_files, 100)))
                )
            ).scalars().all()
        else:
            file_records = (
                await db.execute(
                    select(File)
                    .where(
                        File.owner_user_id == user.id,
                        File.batch_id == input_batch_id,
                        File.file_type.in_(["pdf", "markdown"]),
                    )
                    .order_by(File.original_name.asc())
                    .limit(max(1, min(max_files, 100)))
                )
            ).scalars().all()
        scanned_count = len(file_records)
        for index, record in enumerate(file_records, start=1):
            stored_path = resolve_storage_path(record.storage_path)
            candidates.append(
                {
                    "entry_id": f"batch-{index}",
                    "file_id": record.id,
                    "title": Path(record.original_name).stem,
                    "filename": record.original_name,
                    "relative_path": record.original_name,
                    "extension": Path(record.original_name).suffix.lower(),
                    "size_bytes": record.size_bytes,
                    "md5": record.md5,
                    "preview": _extract_preview(stored_path, record.file_type, max_chars=1400) if stored_path.exists() else "",
                    "source": "upload_batch",
                }
            )
    else:
        if not input_folder_path:
            return {"error": "input_inbox_not_configured", "hint": "请先上传一个文件夹到 AI 助手。"}
        input_folder = Path(input_folder_path)
        if not input_folder.exists() or not input_folder.is_dir():
            return {"error": "input_folder_missing", "path": input_folder_path}
        path_files = _collect_folder_files(input_folder, recursive, max_files)
        scanned_count = len(path_files)
        for index, source_path in enumerate(path_files, start=1):
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
                    "source": "server_folder",
                }
            )

    file_ids = [item["file_id"] for item in candidates if item.get("file_id")]
    entries_by_file_id: dict[str, BibEntry] = {}
    if file_ids:
        existing_entries = (
            await db.execute(
                select(BibEntry).where(
                    BibEntry.owner_user_id == user.id,
                    or_(
                        BibEntry.source_file_id.in_(file_ids),
                        BibEntry.markdown_source_file_id.in_(file_ids),
                    ),
                )
            )
        ).scalars().all()
        for entry in existing_entries:
            if entry.source_file_id:
                entries_by_file_id[str(entry.source_file_id)] = entry
            if entry.markdown_source_file_id:
                entries_by_file_id[str(entry.markdown_source_file_id)] = entry
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
        exact_entry = entries_by_file_id.get(str(item.get("file_id") or ""))
        best_entry = None
        best_score = 0.0
        if exact_entry is None:
            for entry in library_entries:
                if item.get("file_id") and item.get("file_id") in {entry.source_file_id, entry.markdown_source_file_id}:
                    continue
                score = title_match_score(item["title"], entry.title or "")
                if score > best_score:
                    best_score = score
                    best_entry = entry
        if exact_entry is not None:
            library_match = {
                "status": "in_library",
                "method": "file_binding",
                "score": 1.0,
                "entry_id": exact_entry.id,
                "library_title": exact_entry.title,
                "file_id": item.get("file_id") or exact_entry.source_file_id or exact_entry.markdown_source_file_id,
                "reading_status": exact_entry.reading_status,
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
        elif item.get("file_id"):
            library_match = {
                "status": "file_exists_no_bib_entry",
                "method": "uploaded_file",
                "score": round(best_score, 3),
                "entry_id": None,
                "library_title": best_entry.title if best_entry else None,
                "file_id": item.get("file_id"),
                "reading_status": None,
            }
        else:
            library_match = {
                "status": "not_in_library",
                "method": "file_binding_and_title",
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
                "file_id": item.get("file_id") or "",
                "relevant": relevant,
                "confidence": confidence,
                "library_match": library_match,
                "reason": "topic=*，全部列出。" if all_topic else (row.get("reason") or ""),
            }
        )

    summary = _summarize_scan_result(
        source=source_label,
        topic=topic,
        scanned=scanned_count,
        rows=rows,
        skipped=skipped,
        input_batch_id=input_batch_id,
    )

    return {
        "input_folder_path": input_folder_path,
        "input_batch_id": input_batch_id,
        "source": source_label,
        "topic": topic,
        "scanned": scanned_count,
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
        "summary": summary,
        "note": "这是只读清单；在线版扫描的是已上传到 AI 助手 inbox 的文件夹批次，未启动精读任务。",
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
    scan = await tool_scan_input_folder(
        db,
        user,
        api_key=api_key,
        topic=topic,
        recursive=recursive,
        max_files=max_files,
        confidence_threshold=confidence_threshold,
    )
    if scan.get("error"):
        return scan
    selected = [
        paper
        for paper in scan.get("papers", [])
        if paper.get("relevant") and paper.get("file_id")
    ]
    batch = None
    if selected:
        batch = await tool_start_batch_reading(
            db,
            user,
            api_key=api_key,
            mode=mode,
            file_ids=[paper["file_id"] for paper in selected],
            analysis_dims=analysis_dims or [],
            custom_question=custom_question,
            extraction_method=extraction_method,
            conflict_resolution=conflict_resolution,
        )
    return {
        **scan,
        "mode": mode,
        "selected_count": len(selected),
        "selected": selected,
        "batch": batch,
    }


def _research_query_from_args(args: dict[str, Any]) -> ResearchQuery:
    raw_limit = int(args.get("limit_entries") or 0)
    return ResearchQuery(
        question=str(args.get("question") or args.get("query") or ""),
        entry_ids=[str(item) for item in (args.get("entry_ids") or []) if item],
        keywords=[str(item) for item in (args.get("keywords") or []) if item],
        include_source_text=bool(args.get("include_source_text", True)),
        include_user_notes=bool(args.get("include_user_notes", True)),
        include_ai_notes=bool(args.get("include_ai_notes", True)),
        limit_entries=0 if raw_limit == 0 else max(1, raw_limit),
        limit_evidence_per_entry=max(1, int(args.get("limit_evidence_per_entry") or 8)),
    )

TOOL_SCHEMAS = REGISTERED_TOOL_SCHEMAS


async def execute_tool(
    name: str,
    args: dict[str, Any],
    *,
    db: AsyncSession,
    user: User,
    api_key: str,
    session: AgentSession,
    progress_callback: Any = None,
) -> dict[str, Any]:
    if name == "research_search":
        return await research_search(db, owner_user_id=user.id, query=_research_query_from_args(args))
    if name == "get_evidence_pack":
        return await get_evidence_pack(db, owner_user_id=user.id, query=_research_query_from_args(args))
    if name == "get_source_windows":
        return await get_source_windows(
            db,
            owner_user_id=user.id,
            entry_ids=[str(item) for item in (args.get("entry_ids") or []) if item],
            question=str(args.get("question") or ""),
            max_windows_per_entry=max(1, min(int(args.get("max_windows_per_entry") or 3), 10)),
        )
    if name == "search_cnki":
        return await tool_search_cnki(
            db,
            user,
            entry_ids=[str(item) for item in (args.get("entry_ids") or []) if item],
            titles=[str(item) for item in (args.get("titles") or []) if item],
            max_items=max(1, int(args.get("max_items") or 50)),
        )
    if name == "lookup_english_fulltext":
        return await tool_lookup_english_fulltext(
            db,
            user,
            entry_ids=[str(item) for item in (args.get("entry_ids") or []) if item],
            max_entries=max(1, int(args.get("max_entries") or 10)),
        )
    if name == "search_library":
        return await tool_search_library(db, user, **args)
    if name == "count_library":
        return await tool_count_library(db, user, **args)
    if name == "analyze_reading_candidates":
        return await analyze_reading_candidates(
            db,
            owner_user_id=user.id,
            topic=str(args.get("topic") or ""),
            reading_status=str(args.get("reading_status") or "none"),
            query=str(args.get("query") or "*"),
            batch_size=int(args.get("batch_size") or 100),
            max_entries=int(args.get("max_entries") or 1200),
            progress_callback=progress_callback,
        )
    if name == "filter_analysis_cache":
        session_state = _json_loads(session.last_state_json, {}) or {}
        cached_dataset = session_state.get("analysis_cache") or {}
        if not isinstance(cached_dataset, dict) or not isinstance(cached_dataset.get("entries"), list):
            return {
                "error": RuntimeNoticeCode.CONTEXT_REQUIRED.value,
                "code": RuntimeNoticeCode.ANALYSIS_CACHE_REQUIRED.value,
                "message": "当前会话没有可复用的分析缓存，请先完成一次批量分析。",
                "suggested_tools": ["analyze_reading_candidates"],
                "recommendations": [
                    "先调用 analyze_reading_candidates 对目标文献集合做批量分析。",
                    "如果想放弃上一轮结果，请明确要求重新全量分析。",
                ],
            }
        return filter_analysis_cache(
            analysis_cache=cached_dataset,
            topic=str(args.get("topic") or ""),
            journal_tier_labels=[str(item) for item in (args.get("journal_tier_labels") or []) if str(item).strip()],
            cluster_labels=[str(item) for item in (args.get("cluster_labels") or []) if str(item).strip()],
            require_fulltext=args.get("require_fulltext"),
            reading_status=str(args.get("reading_status") or ""),
            max_entries=int(args.get("max_entries") or 0),
        )
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
            "note": "这是执行提案预览；确认后才会对已上传的文件启动精读任务。",
        }
        return await _create_proposal(db, user, session, action_type=name, arguments=args, preview=preview)
    if name == "get_job_status":
        return await tool_get_job_status(db, user, **args)
    return {"error": f"unknown_tool:{name}"}


def build_messages(
    req: AgentChatRequest,
    *,
    extra_system_contents: list[str] | None = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "你是 Deep Reading Agent 的文献工作台助手。你可以调用工具检索文献库、查看精读结果、"
                "启动精读任务、查询任务状态，并基于工具返回的真实数据做对比和综述。"
                "在线版的文件夹来源是用户主动上传到 AI 助手 inbox 的 PDF/Markdown 批次，"
                "不要要求用户提供本地路径，也不要尝试读取任意服务器路径。"
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
    messages.append(
        {
            "role": "system",
            "content": (
                "研究 Agent 证据规则：回答研究性问题前，优先调用 research_search 或 get_evidence_pack 检索本地文献库。"
                "证据按 P0 原文/题录摘要、P1 用户或人工编辑笔记、P2 AI 笔记、P3 临时联网结果分级；"
                "P0 与 P1/P2 冲突时以 P0 为准，P1 与 P2 冲突时以 P1 为准，并说明冲突。"
                "回答要说明检索了什么、主要依据哪些 source_tier、结论、限制。"
                "如果用户是在问文献数量、总数、多少篇，优先调用 count_library 直接读取数据库计数；"
                "不要先罗列标题，也不要把 search_library 当前返回页误当成总量。"
                "如果用户是在要求对大量文献做分类总结、生成表格、推荐优先精读对象，优先调用 analyze_reading_candidates；"
                "该工具会分批处理文献、写入结构化工作笔记，并输出候选表格。"
                "search_cnki 和 lookup_english_fulltext 是联网/外部检索工具；只有用户明确要求 CNKI、打开网页、查英文全文、找 PDF 或外部检索时才调用。"
                "这两个工具返回的是临时 P3 线索和 open_urls，前端会协助批量打开新标签页；不得声称这些结果已经保存进数据库。"
                "写库、启动任务、应用在线匹配等动作必须走 proposal，不得在普通回答中假装已经执行。"
                "limit_entries 参数：默认搜索全部文献（limit_entries=0）。如需缩小范围可设 limit_entries>0。"
            ),
        }
    )
    for content in extra_system_contents or []:
        if str(content or "").strip():
            messages.append({"role": "system", "content": str(content)})
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
        raise HTTPException(status_code=400, detail=classify_agent_exception(exc, stage="input_validation"))

    provider = resolve_llm_provider(api_key).provider
    client = create_openai_client(
        api_key,
        timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
    )
    model = model_for_api_key(api_key, MODEL)

    async def _stream():
        session: AgentSession | None = None
        state: dict[str, Any] = {}
        error_stage = "session_setup"
        active_tool: str | None = None
        try:
            session = await _ensure_session(db, user, req)
            state = _json_loads(session.last_state_json, {}) or {}
            task_frame = build_task_frame(req.message, state)
            resolved_context = resolve_context_refs(task_frame, state)
            state["last_runtime_notice"] = None
            state["last_stop_summary"] = None
            state["last_agent_error"] = None
            state["active_task_frame"] = task_frame
            state["resolved_context"] = {
                "status": resolved_context.get("status"),
                "source": resolved_context.get("source"),
                "count": resolved_context.get("count", 0),
                "entries": (resolved_context.get("entries") or [])[:8],
            }
            await _replace_session_state(db, session, state=state)
            yield sse_event(
                "session",
                {
                    "session_id": session.id,
                    "title": session.title,
                    "last_state": summarize_state_for_ui(state),
                },
            )
            await _save_agent_message(db, user, session, role="user", event_type="message", content=req.message)
            await db.commit()

            runtime_prompts = build_runtime_system_prompts(task_frame, resolved_context, state)
            if state:
                runtime_prompts.append(
                    "当前持久会话结构化状态摘要：" + json.dumps(summarize_state_for_ui(state), ensure_ascii=False)[:4000]
                )
            messages = build_messages(req, extra_system_contents=runtime_prompts)

            for _ in range(MAX_TOOL_ROUNDS):
                error_stage = "llm_completion"
                active_tool = None
                response = client.chat.completions.create(
                    model=model,
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
                    active_tool = name
                    error_stage = "tool_argument_parse"
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    normalized_args = normalize_tool_args(
                        name,
                        args,
                        task_frame=task_frame,
                        resolved_context=resolved_context,
                        state=state,
                    )
                    yield sse_event("tool_call", {"name": name, "arguments": normalized_args})
                    await _save_agent_message(
                        db,
                        user,
                        session,
                        role="assistant",
                        event_type="tool_call",
                        tool_name=name,
                        payload=normalized_args,
                    )
                    policy_result = enforce_tool_policy(
                        name,
                        normalized_args,
                        task_frame=task_frame,
                        state=state,
                        resolved_context=resolved_context,
                    )
                    if policy_result is not None:
                        result = policy_result
                    else:
                        error_stage = "tool_execution"
                        if name == "analyze_reading_candidates":
                            progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

                            async def _on_progress(payload: dict[str, Any]) -> None:
                                await progress_queue.put(payload)

                            tool_task = asyncio.create_task(
                                execute_tool(
                                    name,
                                    normalized_args,
                                    db=db,
                                    user=user,
                                    api_key=api_key,
                                    session=session,
                                    progress_callback=_on_progress,
                                )
                            )
                            while True:
                                if tool_task.done() and progress_queue.empty():
                                    break
                                try:
                                    payload = await asyncio.wait_for(progress_queue.get(), timeout=0.2)
                                except asyncio.TimeoutError:
                                    continue
                                working_note = payload.get("working_note")
                                if isinstance(working_note, dict):
                                    state = append_working_note(state, working_note)
                                    await _replace_session_state(db, session, state=state)
                                    await db.commit()
                                    yield sse_event("session_state", {"last_state": summarize_state_for_ui(state)})
                                yield sse_event("analysis_progress", payload)
                            result = await tool_task
                        else:
                            result = await execute_tool(
                                name,
                                normalized_args,
                                db=db,
                                user=user,
                                api_key=api_key,
                                session=session,
                            )
                    state = update_state_after_tool(
                        state,
                        name=name,
                        args=normalized_args,
                        result=result,
                        blocked_by_policy=policy_result is not None,
                    )
                    if name == "scan_input_folder":
                        state["last_scan"] = result
                    error_stage = "session_persistence"
                    await _replace_session_state(db, session, state=state)
                    resolved_context = resolve_context_refs(task_frame, state)
                    await _save_agent_message(
                        db,
                        user,
                        session,
                        role="tool",
                        event_type="tool_result",
                        tool_name=name,
                        payload=result,
                    )
                    if isinstance(result, dict) and result.get("proposal_id"):
                        yield sse_event("proposal", result)
                    await db.commit()
                    yield sse_event("session_state", {"last_state": summarize_state_for_ui(state)})
                    if state.get("last_runtime_notice"):
                        yield sse_event("runtime_notice", state["last_runtime_notice"])
                    yield sse_event("tool_result", {"name": name, "result": result})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    )
                    active_tool = None
                    error_stage = "llm_completion"

            stop_summary = build_stop_summary(
                task_frame=task_frame,
                state=state,
                reason="max_tool_rounds_reached",
                max_tool_rounds=MAX_TOOL_ROUNDS,
            )
            state["last_stop_summary"] = stop_summary
            await _replace_session_state(db, session, state=state)
            await db.commit()
            yield sse_event("session_state", {"last_state": summarize_state_for_ui(state)})
            yield sse_event("runtime_notice", stop_summary)
            yield sse_event(
                "answer",
                {
                    "content": stop_summary["message"]
                },
            )
            yield sse_event("done", {})
        except Exception as exc:
            payload = classify_agent_exception(exc, stage=error_stage, provider=provider, tool=active_tool)
            try:
                if session is not None:
                    state["last_agent_error"] = payload
                    await _replace_session_state(db, session, state=state)
                    await _save_agent_message(
                        db,
                        user,
                        session,
                        role="assistant",
                        event_type="error",
                        content=payload.get("message", ""),
                        payload=payload,
                    )
                    await db.commit()
                    yield sse_event("session_state", {"last_state": summarize_state_for_ui(state)})
            except Exception:
                await db.rollback()
            yield sse_event("error", payload)

    return StreamingResponse(_stream(), media_type="text/event-stream")
