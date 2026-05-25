"""Library AI chat router for natural-language bibliography queries."""
from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from auth.dependencies import current_user
from backend.utils.api_key import validate_deepseek_key
from db import get_db
from db.models import Annotation, Artifact, BibEntry, BibReference, Job, JobBibEntry, ReadingItem, User
from prompt_service import get_effective_prompt_text
from result_storage import build_result_storage_path, get_results_root

router = APIRouter()


class LibraryChatTurn(BaseModel):
    question: str
    report: str = ""
    entry_ids: list[str] = Field(default_factory=list)
    entry_titles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    result_count: int = 0


class LibraryChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    api_key: Optional[str] = None
    history: list[LibraryChatTurn] = Field(default_factory=list, max_length=12)
    scope_mode: Literal["auto", "library", "previous_results"] = "auto"


class LibraryChatCommentRequest(BaseModel):
    turn_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=4000)
    report: str = Field(min_length=1, max_length=80000)
    entry_ids: list[str] = Field(min_length=1, max_length=200)
    history: list[LibraryChatTurn] = Field(default_factory=list, max_length=12)
    api_key: Optional[str] = None


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _clean_terms(value) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        normalized = text.casefold()
        if text and normalized not in seen:
            seen.add(normalized)
            result.append(text)
    return result


def _tag_action(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    action_type = value.get("type")
    if action_type not in {"add_tags", "remove_tags"}:
        return None
    tags = _clean_terms(value.get("tags"))[:20]
    if not tags:
        return None
    return {"type": action_type, "tags": tags}


def _optional_year(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _history_for_parser(history: list[LibraryChatTurn]) -> list[dict]:
    return [
        {
            "question": turn.question,
            "result_count": turn.result_count,
            "keywords": turn.keywords[:24],
            "entry_titles": turn.entry_titles[:60],
        }
        for turn in history[-6:]
    ]


def _history_for_report(history: list[LibraryChatTurn]) -> list[dict]:
    return [
        {
            "question": turn.question,
            "report": turn.report,
            "result_count": turn.result_count,
            "keywords": turn.keywords[:24],
        }
        for turn in history[-4:]
    ]


def _build_query_user_message(req: LibraryChatRequest) -> str:
    payload = {
        "scope_mode": req.scope_mode,
        "current_question": req.question.strip(),
        "history": _history_for_parser(req.history),
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_papers_text(rows: list[BibEntry], read_entry_ids: set[str]) -> str:
    status_map = {
        "none": "未进入精读",
        "has_pdf": "已有关联文件",
        "reading": "精读中",
        "read": "已完成精读",
    }
    papers: list[str] = []
    for index, row in enumerate(rows, start=1):
        reading_label = "有精读条目" if row.id in read_entry_ids else status_map.get(row.reading_status, row.reading_status)
        authors = ", ".join(_json_list(row.authors_json)) or "作者待补"
        keywords = ", ".join(_json_list(row.keywords_json)) or "关键词缺失"
        papers.append(
            "\n".join(
                [
                    "---",
                    f"**[{index}]** ID：{row.id}",
                    f"标题：{row.title}",
                    f"作者：{authors} | 期刊：{row.journal or '未知'} | 年份：{row.year or '未知'}",
                    f"精读状态：{reading_label}",
                    f"关键词：{keywords}",
                    f"摘要：{row.abstract or '摘要缺失'}",
                    "---",
                ]
            )
        )
    return "\n\n".join(papers)


def _build_report_user_message(
    req: LibraryChatRequest,
    intent: dict,
    rows: list[BibEntry],
    links: list[dict],
    read_entry_ids: set[str],
) -> str:
    payload = {
        "history": _history_for_report(req.history),
        "current_question": req.question.strip(),
        "search_intent": intent,
        "result_count": len(rows),
        "citation_links": links,
    }
    return (
        "## 查询上下文\n"
        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
        f"## 本轮命中文献全集\n{_build_papers_text(rows, read_entry_ids)}"
    )


def _build_comment_user_message(
    req: LibraryChatCommentRequest,
    rows: list[BibEntry],
) -> str:
    payload = {
        "current_question": req.question.strip(),
        "current_report": req.report.strip(),
        "history": _history_for_report(req.history),
        "papers": [
            {
                "entry_id": row.id,
                "title": row.title,
                "authors": _json_list(row.authors_json),
                "journal": row.journal,
                "year": row.year,
                "keywords": _json_list(row.keywords_json),
                "abstract": row.abstract,
            }
            for row in rows
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_tag_target_user_message(
    req: LibraryChatRequest,
    intent: dict,
    rows: list[BibEntry],
    candidate_numbers: dict[str, int],
) -> str:
    payload = {
        "current_question": req.question.strip(),
        "search_intent": intent,
        "history": [
            {
                "question": turn.question,
                "report": turn.report,
                "result_count": turn.result_count,
                "keywords": turn.keywords[:24],
            }
            for turn in req.history[-3:]
        ],
        "candidates": [
            {
                "candidate_number": candidate_numbers.get(row.id),
                "entry_id": row.id,
                "title": row.title,
                "authors": _json_list(row.authors_json),
                "journal": row.journal,
                "year": row.year,
                "keywords": _json_list(row.keywords_json),
                "abstract": row.abstract,
            }
            for row in rows
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _entry_ids_from_question_numbers(question: str, candidate_numbers: dict[str, int]) -> list[str]:
    number_to_entry_id = {number: entry_id for entry_id, number in candidate_numbers.items()}
    entry_ids: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"(?:\[(\d{1,6})\]|(?<!\d)(\d{1,6})\s*号|第\s*(\d{1,6})\s*(?:篇|篇文献|文献))", question):
        number = int(match.group(1) or match.group(2) or match.group(3))
        entry_id = number_to_entry_id.get(number)
        if entry_id and entry_id not in seen:
            seen.add(entry_id)
            entry_ids.append(entry_id)
    return entry_ids


def _parse_target_entry_ids(
    value,
    allowed_entry_ids: set[str],
    candidate_numbers: dict[str, int],
) -> list[str]:
    rows = value.get("entry_ids") if isinstance(value, dict) else None
    candidate_rows = value.get("candidate_numbers") if isinstance(value, dict) else None
    if not isinstance(rows, list) and not isinstance(candidate_rows, list):
        return []

    number_to_entry_id = {str(number): entry_id for entry_id, number in candidate_numbers.items()}
    entry_ids: list[str] = []
    seen: set[str] = set()

    for row in rows or []:
        entry_id = str(row or "").strip()
        entry_id = number_to_entry_id.get(entry_id, entry_id)
        if entry_id in allowed_entry_ids and entry_id not in seen:
            seen.add(entry_id)
            entry_ids.append(entry_id)

    for row in candidate_rows or []:
        entry_id = number_to_entry_id.get(str(row or "").strip())
        if entry_id in allowed_entry_ids and entry_id not in seen:
            seen.add(entry_id)
            entry_ids.append(entry_id)

    return entry_ids


def _parse_comment_rows(value, allowed_entry_ids: set[str]) -> dict[str, str]:
    rows = value.get("comments") if isinstance(value, dict) else None
    if not isinstance(rows, list):
        return {}

    comments: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry_id = str(row.get("entry_id") or "").strip()
        note = str(row.get("comment") or "").strip()
        if entry_id in allowed_entry_ids and note:
            comments[entry_id] = note
    return comments


@router.post("")
async def library_chat(
    req: LibraryChatRequest,
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
    query_prompt = await get_effective_prompt_text(
        db,
        user_id=user.id,
        prompt_type="library_chat",
        prompt_key="query_parser",
    )
    report_prompt = await get_effective_prompt_text(
        db,
        user_id=user.id,
        prompt_type="library_chat",
        prompt_key="report_writer",
    )
    tag_target_prompt = await get_effective_prompt_text(
        db,
        user_id=user.id,
        prompt_type="library_chat",
        prompt_key="tag_target_selector",
    )

    async def _stream():
        try:
            query_response = client.chat.completions.create(
                model="deepseek-v4-flash",
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": query_prompt},
                    {"role": "user", "content": _build_query_user_message(req)},
                ],
                temperature=0.1,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            query_raw = query_response.choices[0].message.content or "{}"
            query_data = json.loads(query_raw)
            previous_entry_ids = req.history[-1].entry_ids if req.history else []
            parsed_scope = "previous_results" if query_data.get("scope") == "previous_results" else "library"
            scope = req.scope_mode if req.scope_mode != "auto" else parsed_scope
            if scope == "previous_results" and not previous_entry_ids:
                scope = "library"

            core_keywords = _clean_terms(query_data.get("core_keywords"))
            expanded_keywords = _clean_terms(query_data.get("expanded_keywords"))
            search_terms = _clean_terms([*core_keywords, *expanded_keywords])
            journal = str(query_data.get("journal") or "").strip() or None
            authors = _clean_terms(query_data.get("authors"))
            tag_action = _tag_action(query_data.get("tag_action"))
            year_from = _optional_year(query_data.get("year_from"))
            year_to = _optional_year(query_data.get("year_to"))
            intent = {
                "scope": scope,
                "core_keywords": core_keywords,
                "expanded_keywords": expanded_keywords,
                "journal": journal,
                "year_from": year_from,
                "year_to": year_to,
                "authors": authors,
                "tag_action": tag_action,
            }
            yield sse_event("intent", intent)

            stmt = select(BibEntry).where(BibEntry.owner_user_id == user.id)
            if scope == "previous_results":
                stmt = stmt.where(BibEntry.id.in_(previous_entry_ids))
            # Previous-result tag actions need semantic target selection from the whole
            # prior result set. Literal keyword matching here can silently drop papers
            # that the prior AI report selected by abstract-level relevance.
            use_keyword_recall = not (tag_action and scope == "previous_results")
            if search_terms and use_keyword_recall:
                keyword_conditions = []
                for term in search_terms:
                    like = f"%{term}%"
                    keyword_conditions.append(
                        or_(
                            BibEntry.title.ilike(like),
                            BibEntry.abstract.ilike(like),
                            BibEntry.keywords_json.ilike(like),
                        )
                    )
                stmt = stmt.where(or_(*keyword_conditions))
            if journal:
                stmt = stmt.where(BibEntry.journal.ilike(f"%{journal}%"))
            if year_from is not None:
                stmt = stmt.where(BibEntry.year >= year_from)
            if year_to is not None:
                stmt = stmt.where(BibEntry.year <= year_to)
            for author in authors:
                stmt = stmt.where(BibEntry.authors_json.ilike(f"%{author}%"))

            rows = (await db.execute(stmt.order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc()))).scalars().all()
            if scope == "previous_results":
                previous_order = {entry_id: index for index, entry_id in enumerate(previous_entry_ids)}
                rows.sort(key=lambda row: previous_order.get(row.id, len(previous_order)))

            if tag_action and rows:
                candidate_numbers = (
                    {entry_id: index + 1 for index, entry_id in enumerate(previous_entry_ids)}
                    if scope == "previous_results"
                    else {row.id: index + 1 for index, row in enumerate(rows)}
                )
                explicit_target_ids = _entry_ids_from_question_numbers(req.question, candidate_numbers)
                target_response = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": tag_target_prompt},
                        {
                            "role": "user",
                            "content": _build_tag_target_user_message(
                                req,
                                intent,
                                rows,
                                candidate_numbers,
                            ),
                        },
                    ],
                    temperature=0.1,
                    max_tokens=4000,
                    response_format={"type": "json_object"},
                )
                target_raw = target_response.choices[0].message.content or "{}"
                target_ids = [
                    *explicit_target_ids,
                    *_parse_target_entry_ids(
                        json.loads(target_raw),
                        {row.id for row in rows},
                        candidate_numbers,
                    ),
                ]
                target_ids = list(dict.fromkeys(target_ids))
                target_id_set = set(target_ids)
                rows_by_id = {row.id: row for row in rows if row.id in target_id_set}
                rows = [rows_by_id[entry_id] for entry_id in target_ids if entry_id in rows_by_id]

            entry_ids = [row.id for row in rows]
            titles = [row.title for row in rows]
            id_to_title = {row.id: row.title for row in rows}
            yield sse_event(
                "results",
                {
                    "entry_ids": entry_ids,
                    "entry_titles": titles,
                    "count": len(entry_ids),
                    "scope": scope,
                },
            )
            if tag_action:
                yield sse_event(
                    "action_proposal",
                    {
                        "type": tag_action["type"],
                        "tags": tag_action["tags"],
                        "entry_ids": entry_ids,
                        "entry_titles": titles,
                        "count": len(entry_ids),
                        "scope": scope,
                        "journal": journal,
                    },
                )

            ref_rows = []
            if entry_ids:
                ref_rows = (
                    await db.execute(
                        select(BibReference).where(
                            BibReference.owner_user_id == user.id,
                            BibReference.source_bib_entry_id.in_(entry_ids),
                            BibReference.matched_bib_entry_id.in_(entry_ids),
                        )
                    )
                ).scalars().all()
            links = [
                {
                    "from_id": ref.source_bib_entry_id,
                    "to_id": ref.matched_bib_entry_id,
                    "from_title": id_to_title.get(ref.source_bib_entry_id, ""),
                    "to_title": id_to_title.get(ref.matched_bib_entry_id or "", ""),
                }
                for ref in ref_rows
            ]
            yield sse_event("citations", {"links": links})

            reading_rows = []
            if entry_ids:
                reading_rows = (
                    await db.execute(
                        select(ReadingItem.bib_entry_id)
                        .where(
                            ReadingItem.bib_entry_id.in_(entry_ids),
                            ReadingItem.owner_user_id == user.id,
                        )
                        .distinct()
                    )
                ).scalars().all()
            report_stream = client.chat.completions.create(
                model="deepseek-v4-flash",
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": report_prompt},
                    {
                        "role": "user",
                        "content": _build_report_user_message(
                            req,
                            intent,
                            rows,
                            links,
                            set(reading_rows),
                        ),
                    },
                ],
                temperature=0.65,
                max_tokens=16000,
                stream=True,
            )
            for chunk in report_stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield sse_event("report", {"content": delta.content})
            yield sse_event(
                "done",
                {
                    "entry_ids": entry_ids,
                    "entry_titles": titles,
                    "keywords": search_terms,
                    "count": len(entry_ids),
                    "scope": scope,
                },
            )
        except Exception as exc:
            yield sse_event("error", {"message": str(exc)})

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/comments")
async def save_library_chat_comments(
    req: LibraryChatCommentRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        api_key = validate_deepseek_key(req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    requested_ids = list(dict.fromkeys(entry_id.strip() for entry_id in req.entry_ids if entry_id.strip()))
    rows = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.id.in_(requested_ids),
                BibEntry.owner_user_id == user.id,
            )
        )
    ).scalars().all()
    rows_by_id = {row.id: row for row in rows}
    ordered_rows = [rows_by_id[entry_id] for entry_id in requested_ids if entry_id in rows_by_id]
    if not ordered_rows:
        raise HTTPException(status_code=404, detail="No owned bibliography entries found for this chat turn.")

    comment_prompt = await get_effective_prompt_text(
        db,
        user_id=user.id,
        prompt_type="library_chat",
        prompt_key="paper_comment_writer",
    )
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
    )

    comments: dict[str, str] = {}
    chunk_size = 30
    for start in range(0, len(ordered_rows), chunk_size):
        chunk = ordered_rows[start : start + chunk_size]
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            extra_body={"thinking": {"type": "disabled"}},
            messages=[
                {"role": "system", "content": comment_prompt},
                {"role": "user", "content": _build_comment_user_message(req, chunk)},
            ],
            temperature=0.2,
            max_tokens=12000,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        comments.update(_parse_comment_rows(parsed, {row.id for row in chunk}))

    await db.execute(
        delete(Annotation).where(
            Annotation.owner_user_id == user.id,
            Annotation.source_type == "library_note",
            Annotation.source_id == req.turn_id,
            Annotation.is_ai_generated == 1,
        )
    )
    for entry_id in requested_ids:
        note = comments.get(entry_id)
        if not note or entry_id not in rows_by_id:
            continue
        db.add(
            Annotation(
                id=str(uuid.uuid4()),
                owner_user_id=user.id,
                source_type="library_note",
                source_id=req.turn_id,
                bib_entry_id=entry_id,
                selected_text=req.question.strip(),
                note=note,
                is_ai_generated=1,
            )
        )
    await db.commit()
    return {
        "requested": len(requested_ids),
        "matched": len(ordered_rows),
        "saved": len(comments),
        "skipped": len(ordered_rows) - len(comments),
    }


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _compute_expires_at(user: User) -> datetime | None:
    if user.role == "normal":
        return _utcnow_naive() + __import__("datetime").timedelta(hours=24)
    return None


class SaveReportRequest(BaseModel):
    question: str
    report: str
    entry_ids: list[str] = Field(default_factory=list)
    entry_titles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


@router.post("/save-report")
async def save_chat_report(
    req: SaveReportRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not req.report.strip():
        raise HTTPException(status_code=400, detail="报告内容不能为空。")

    members: list[BibEntry] = []
    seen: set[str] = set()
    for entry_id in req.entry_ids:
        entry = await db.get(BibEntry, entry_id)
        if entry is None or entry.owner_user_id != user.id or entry.id in seen:
            continue
        seen.add(entry.id)
        members.append(entry)

    job_id = str(uuid.uuid4())
    now = _utcnow_naive()
    db.add(
        Job(
            id=job_id,
            owner_user_id=user.id,
            job_type="library_chat",
            status="success",
            params_json=json.dumps(
                {"question": req.question, "keywords": req.keywords},
                ensure_ascii=False,
            ),
            progress=100,
            current_stage="完成",
            created_at=now,
            started_at=now,
            finished_at=now,
            expires_at=_compute_expires_at(user),
        )
    )

    for sort_order, entry in enumerate(members):
        db.add(
            JobBibEntry(
                job_id=job_id,
                bib_entry_id=entry.id,
                role="library_chat_member",
                sort_order=sort_order,
            )
        )

    results_root = get_results_root()
    result_dir = results_root / str(user.id) / job_id
    result_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"library_chat_{timestamp}.md"

    papers_str = ", ".join(req.entry_titles[:3])
    if len(req.entry_titles) > 3:
        papers_str += f" 等{len(req.entry_titles)}篇"

    content = f"""# 文献助手报告：{req.question}

**生成时间**：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**涉及文献**：{papers_str}
**检索关键词**：{', '.join(req.keywords) if req.keywords else '无'}

---

{req.report}
"""

    filepath = result_dir / filename
    filepath.write_text(content, encoding="utf-8")
    storage_path = build_result_storage_path(filepath)
    db.add(
        Artifact(
            job_id=job_id,
            owner_user_id=user.id,
            artifact_type="library_chat_md",
            filename=filename,
            storage_path=storage_path,
            size_bytes=filepath.stat().st_size,
            expires_at=_compute_expires_at(user),
        )
    )
    await db.commit()

    return {"success": True, "filename": filename, "path": storage_path, "job_id": job_id}
