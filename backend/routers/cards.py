from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from backend.utils.api_key import validate_deepseek_key
from cleanup import compute_expires_at_for_role, utcnow_naive
from db import get_db
from db.models import Artifact, BibEntry, CardNote, File, User
from prompt_service import get_effective_prompt_text
from services.card_notes import (
    build_card_markdown,
    build_paper_markdown,
    card_note_basename,
    delete_card_mirror,
    json_list,
    paper_note_basename,
    read_artifact_markdown,
    read_markdown_file,
    strip_frontmatter,
    write_card_mirror,
)

router = APIRouter()


class CardFromSelectionRequest(BaseModel):
    source_bib_entry_id: str
    source_version: str = Field(pattern="^(original|translated)$")
    source_markdown_file_id: Optional[str] = None
    source_translation_artifact_id: Optional[int] = None
    selected_text: str = Field(min_length=1, max_length=20000)
    context_before: str = Field(default="", max_length=20000)
    context_after: str = Field(default="", max_length=20000)
    user_prompt: str = Field(default="", max_length=4000)
    api_key: str


class CardUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    summary: Optional[str] = Field(default=None, max_length=4000)
    tags: Optional[list[str]] = Field(default=None, max_length=30)
    body_markdown: Optional[str] = Field(default=None, min_length=1, max_length=60000)


def _dt(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _clean_tags(tags: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        text = str(tag).strip().lstrip("#")
        if not text or text.casefold() in seen:
            continue
        seen.add(text.casefold())
        cleaned.append(text)
    return cleaned[:30]


def card_response(card: CardNote, entry: BibEntry | None = None) -> dict:
    return {
        "id": card.id,
        "source_bib_entry_id": card.source_bib_entry_id,
        "source_title": entry.title if entry is not None else None,
        "source_version": card.source_version,
        "source_markdown_file_id": card.source_markdown_file_id,
        "source_translation_artifact_id": card.source_translation_artifact_id,
        "title": card.title,
        "summary": card.summary,
        "tags": json_list(card.tags_json),
        "selected_text": card.selected_text,
        "context_before": card.context_before,
        "context_after": card.context_after,
        "user_prompt": card.user_prompt,
        "body_markdown": card.body_markdown,
        "storage_path": card.storage_path,
        "created_at": _dt(card.created_at),
        "updated_at": _dt(card.updated_at),
    }


async def get_owned_entry(db: AsyncSession, user: User, entry_id: str) -> BibEntry:
    entry = (
        await db.execute(
            select(BibEntry).where(BibEntry.id == entry_id, BibEntry.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bib entry not found")
    return entry


async def get_owned_card(db: AsyncSession, user: User, card_id: str) -> CardNote:
    card = (
        await db.execute(
            select(CardNote).where(CardNote.id == card_id, CardNote.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")
    return card


def _parse_card_json(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json").strip()
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        raw = raw[first : last + 1]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 返回的卡片不是有效 JSON，请重试或调整提示词。",
        ) from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="AI 返回的卡片结构无效。")
    return data


async def generate_card_payload(
    db: AsyncSession,
    *,
    user: User,
    entry: BibEntry,
    request: CardFromSelectionRequest,
) -> dict:
    api_key = validate_deepseek_key(request.api_key)
    system_prompt = await get_effective_prompt_text(
        db,
        user_id=user.id,
        prompt_type="card_note",
        prompt_key="atomic_card_writer",
    )
    metadata = {
        "title": entry.title,
        "authors": json_list(entry.authors_json),
        "year": entry.year,
        "journal": entry.journal,
        "doi": entry.doi,
        "keywords": json_list(entry.keywords_json),
        "abstract": entry.abstract,
    }
    user_prompt = f"""
请基于以下论文选段生成一张中文原子阅读卡。

【当前阅读版本】
{request.source_version}

【论文元数据】
{json.dumps(metadata, ensure_ascii=False, indent=2)}

【选中原文】
{request.selected_text}

【上文】
{request.context_before}

【下文】
{request.context_after}

【用户补充要求】
{request.user_prompt or "无"}

请只输出 JSON，字段必须包含：
title, summary, tags, body_markdown
""".strip()

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=180.0)
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=2500,
    )
    content = response.choices[0].message.content or ""
    data = _parse_card_json(content)
    title = str(data.get("title") or "").strip()
    body_markdown = str(data.get("body_markdown") or "").strip()
    if not title or not body_markdown:
        raise HTTPException(status_code=502, detail="AI 返回缺少 title 或 body_markdown。")
    return {
        "title": title[:500],
        "summary": str(data.get("summary") or "").strip() or None,
        "tags": _clean_tags(data.get("tags") if isinstance(data.get("tags"), list) else []),
        "body_markdown": body_markdown,
    }


@router.post("/from-selection")
async def create_card_from_selection(
    request: CardFromSelectionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await get_owned_entry(db, user, request.source_bib_entry_id)
    markdown_file_id = request.source_markdown_file_id
    translation_artifact_id = request.source_translation_artifact_id

    if request.source_version == "original":
        markdown_file_id = markdown_file_id or entry.markdown_source_file_id or entry.source_file_id
        source_file = await db.get(File, markdown_file_id) if markdown_file_id else None
        if source_file is None or source_file.owner_user_id != user.id or source_file.file_type != "markdown":
            raise HTTPException(status_code=400, detail="当前文献没有可用于制卡的 Markdown 原文。")
        translation_artifact_id = None
    else:
        artifact = await db.get(Artifact, translation_artifact_id) if translation_artifact_id else None
        if artifact is None or artifact.owner_user_id != user.id or artifact.artifact_type != "translation_md":
            raise HTTPException(status_code=400, detail="当前文献没有可用于制卡的译文 Markdown。")
        markdown_file_id = None

    generated = await generate_card_payload(db, user=user, entry=entry, request=request)
    now = utcnow_naive()
    card = CardNote(
        id=str(uuid4()),
        owner_user_id=user.id,
        source_bib_entry_id=entry.id,
        source_version=request.source_version,
        source_markdown_file_id=markdown_file_id,
        source_translation_artifact_id=translation_artifact_id,
        title=generated["title"],
        summary=generated["summary"],
        tags_json=json.dumps(generated["tags"], ensure_ascii=False),
        selected_text=request.selected_text.strip(),
        context_before=request.context_before.strip() or None,
        context_after=request.context_after.strip() or None,
        user_prompt=request.user_prompt.strip() or None,
        body_markdown=generated["body_markdown"],
        created_at=now,
        updated_at=now,
        expires_at=compute_expires_at_for_role(user.role, now),
    )
    db.add(card)
    await db.flush()
    card.storage_path = write_card_mirror(card, entry)
    await db.commit()
    await db.refresh(card)
    return card_response(card, entry)


@router.get("")
async def list_cards(
    entry_id: str = Query(default=""),
    tag: str = Query(default=""),
    q: str = Query(default=""),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CardNote, BibEntry)
        .join(BibEntry, BibEntry.id == CardNote.source_bib_entry_id)
        .where(CardNote.owner_user_id == user.id)
        .order_by(desc(CardNote.created_at), desc(CardNote.id))
    )
    if entry_id.strip():
        stmt = stmt.where(CardNote.source_bib_entry_id == entry_id.strip())
    rows = (await db.execute(stmt)).all()
    cards = [card_response(card, entry) for card, entry in rows]
    if tag.strip():
        expected = tag.strip().lstrip("#").casefold()
        cards = [card for card in cards if expected in {str(t).casefold() for t in card["tags"]}]
    if q.strip():
        needle = q.strip().casefold()
        cards = [
            card
            for card in cards
            if needle in card["title"].casefold()
            or needle in (card["summary"] or "").casefold()
            or needle in card["body_markdown"].casefold()
            or needle in (card["source_title"] or "").casefold()
        ]
    return cards


@router.get("/export/obsidian")
async def export_cards(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(CardNote, BibEntry)
            .join(BibEntry, BibEntry.id == CardNote.source_bib_entry_id)
            .where(CardNote.owner_user_id == user.id)
            .order_by(CardNote.source_bib_entry_id, CardNote.source_version, CardNote.created_at)
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="暂无可导出的卡片。")

    tmp_path = Path(tempfile.mktemp(suffix=".zip"))
    cards_by_paper: dict[tuple[str, str], list[CardNote]] = {}
    entries: dict[str, BibEntry] = {}
    for card, entry in rows:
        cards_by_paper.setdefault((entry.id, card.source_version), []).append(card)
        entries[entry.id] = entry

    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for card, entry in rows:
            zf.writestr(f"cards/{card_note_basename(card)}.md", build_card_markdown(card, entry))

        for (entry_id, version), cards in cards_by_paper.items():
            entry = entries[entry_id]
            content = ""
            if version == "original":
                file_id = cards[0].source_markdown_file_id or entry.markdown_source_file_id or entry.source_file_id
                source_file = await db.get(File, file_id) if file_id else None
                if source_file and source_file.file_type == "markdown":
                    content = read_markdown_file(source_file.storage_path)
            else:
                artifact_id = cards[0].source_translation_artifact_id
                artifact = await db.get(Artifact, artifact_id) if artifact_id else None
                if artifact and artifact.artifact_type == "translation_md":
                    content = read_artifact_markdown(artifact.storage_path)
            if not content:
                content = f"# {entry.title}\n\n（未找到该版本的 Markdown 正文）\n"
            zf.writestr(
                f"papers/{paper_note_basename(entry, version)}.md",
                build_paper_markdown(entry, version=version, content=strip_frontmatter(content), cards=cards),
            )

    payload = tmp_path.read_bytes()
    tmp_path.unlink(missing_ok=True)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="markdown-card-notes.zip"'},
    )


@router.get("/{card_id}")
async def get_card(
    card_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    card = await get_owned_card(db, user, card_id)
    entry = await db.get(BibEntry, card.source_bib_entry_id)
    return card_response(card, entry)


@router.patch("/{card_id}")
async def update_card(
    card_id: str,
    request: CardUpdateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    card = await get_owned_card(db, user, card_id)
    entry = await get_owned_entry(db, user, card.source_bib_entry_id)
    if request.title is not None:
        card.title = request.title.strip()
    if request.summary is not None:
        card.summary = request.summary.strip() or None
    if request.tags is not None:
        card.tags_json = json.dumps(_clean_tags(request.tags), ensure_ascii=False)
    if request.body_markdown is not None:
        card.body_markdown = request.body_markdown.strip()
    card.updated_at = utcnow_naive()
    delete_card_mirror(card.storage_path)
    card.storage_path = write_card_mirror(card, entry)
    await db.commit()
    await db.refresh(card)
    return card_response(card, entry)


@router.delete("/{card_id}")
async def delete_card(
    card_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    card = await get_owned_card(db, user, card_id)
    delete_card_mirror(card.storage_path)
    await db.delete(card)
    await db.commit()
    return {"ok": True}
