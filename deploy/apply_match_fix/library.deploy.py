"""Library router for bib-entry centric browsing and editing."""
from __future__ import annotations

import json
import logging
import re
import shutil
import hashlib
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import literal, or_, select, func, desc, asc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import get_db
from db.models import Annotation, Artifact, BibAttachment, BibEntry, BibFilterLink, BibReference, CardNote, File, Job, JobBibEntry, ReadingItem, User
from db.utils import title_match_score, normalize_doi, compute_metadata_match_score
from result_storage import resolve_result_path
from services.crossref_source import CrossrefSource
from services.metadata_match_service import apply_high_confidence_match, classify_confidence, score_candidates
from services.metadata_sources import CandidateMetadata
from services.openalex_source import OpenAlexSource
from services.pdf_metadata_extract import extract_front_matter
from services.pdf_metadata_llm import extract_metadata_with_llm
from upload_storage import file_record_exists, resolve_storage_path
from backend.utils.api_key import validate_deepseek_key
from services.abstract_translator import run_batch_translate
from routers.upload import compute_expires_at, detect_file_type, persist_upload_to_temp, utcnow_naive
from upload_storage import build_storage_path, get_user_upload_dir
from services.card_notes import json_list, read_artifact_markdown, read_markdown_file, strip_frontmatter
from services.fulltext_lookup import download_pdf_candidate, lookup_fulltext

router = APIRouter()
logger = logging.getLogger(__name__)


class LibraryEntrySummary(BaseModel):
    id: str
    title: str
    authors: list[str]
    year: Optional[int]
    doi: Optional[str]
    journal: Optional[str]
    reading_status: str
    metadata_completeness: str
    is_pinned: int
    source_db: str
    source_file_id: Optional[str]
    source_file_name: Optional[str]
    source_file_type: Optional[str]
    markdown_source_file_id: Optional[str] = None
    markdown_source_file_name: Optional[str] = None
    language: Optional[str]
    tags: list[str]
    note: Optional[str]
    filter_score: Optional[float] = None
    has_translation: bool = False


class LibraryEntryPageResponse(BaseModel):
    items: list[LibraryEntrySummary]
    total: int
    page: int
    page_size: int
    has_more: bool


class LibraryArtifactResponse(BaseModel):
    id: int
    filename: str
    artifact_type: str
    storage_path: str
    created_at: Optional[str]


class LibraryTimelineItem(BaseModel):
    job_id: str
    job_type: str
    status: str
    created_at: Optional[str]
    finished_at: Optional[str]
    artifacts: list[LibraryArtifactResponse]


class LibraryFilterEvaluation(BaseModel):
    filter_job_id: str
    passed: int
    score: Optional[float]
    reason: Optional[str]
    abstract_translation: Optional[str]
    created_at: Optional[str]


class LibraryAiComment(BaseModel):
    id: str
    source_id: str
    question: Optional[str]
    note: str
    created_at: Optional[str]
    updated_at: Optional[str]


class LibraryEntryDetail(LibraryEntrySummary):
    abstract: Optional[str]
    abstract_cn: Optional[str] = None
    keywords: list[str]
    timeline: list[LibraryTimelineItem]
    filter_evaluations: list[LibraryFilterEvaluation]
    ai_comments: list[LibraryAiComment]
    attachments: list[AttachmentSummary] = Field(default_factory=list)


class AttachmentSummary(BaseModel):
    id: str
    file_id: str
    label: str
    sort_order: int
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    created_at: Optional[str] = None


class AttachmentUpdateRequest(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sort_order: Optional[int] = None


class LibraryEntryUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1)
    authors: Optional[list[str]] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[list[str]] = None
    tags: Optional[list[str]] = None
    note: Optional[str] = None
    is_pinned: Optional[int] = Field(default=None, ge=0, le=1)
    language: Optional[str] = None


class LibraryAiCommentUpdateRequest(BaseModel):
    note: str = Field(min_length=1, max_length=12000)


class BatchTranslateRequest(BaseModel):
    entry_ids: list[str] = Field(..., min_length=1, max_length=200)
    api_key: str


class FullTextCandidateResponse(BaseModel):
    url: str
    source: str
    version: str
    kind: str
    label: str
    confidence: float


class FullTextLookupResponse(BaseModel):
    status: str
    message: str
    attached_file_id: Optional[str] = None
    attached_file_name: Optional[str] = None
    attached_source_url: Optional[str] = None
    doi: Optional[str] = None
    pdf_candidates: list[FullTextCandidateResponse] = Field(default_factory=list)
    landing_pages: list[FullTextCandidateResponse] = Field(default_factory=list)
    working_paper_searches: list[FullTextCandidateResponse] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class ReaderVersion(BaseModel):
    version: str
    label: str
    available: bool


class ReaderCardSummary(BaseModel):
    id: str
    title: str
    summary: Optional[str]
    tags: list[str]
    source_version: str
    created_at: Optional[str]


class ReaderResponse(BaseModel):
    entry: dict
    current_version: str
    versions: list[ReaderVersion]
    markdown: str
    source_markdown_file_id: Optional[str] = None
    source_translation_artifact_id: Optional[int] = None
    cards: list[ReaderCardSummary]
    citations: dict


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _dt(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _clean_optional_text(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _clean_language(value: str | None) -> str | None:
    language = _clean_optional_text(value)
    if language is None:
        return None
    if language not in {"en", "zh", "other"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported bibliography language.",
        )
    return language


def _load_abstract_translation_from_artifact(entry: BibEntry, artifact: Artifact | None) -> Optional[str]:
    if artifact is None:
        return None
    target_path = resolve_result_path(artifact.storage_path)
    if not target_path.exists() or target_path.suffix.lower() not in {".xlsx", ".xls"}:
        return None

    import pandas as pd

    try:
        df = pd.read_excel(target_path, engine="openpyxl")
    except Exception:
        return None

    translation_columns = [
        "abstract_cn",
        "Abstract_CN",
        "abstract_zh",
        "摘要翻译",
        "中文摘要",
        "Abstract Translation",
    ]
    available_translation_columns = [col for col in translation_columns if col in df.columns]
    if not available_translation_columns:
        return None

    candidates = df
    if entry.doi and "DOI" in df.columns:
        candidates = df[df["DOI"].astype(str).str.strip() == entry.doi]
    elif "Title" in df.columns:
        candidates = df[df["Title"].astype(str).str.strip() == entry.title]

    if candidates.empty:
        return None

    row = candidates.iloc[0]
    for column in available_translation_columns:
        text = _clean_optional_text(row.get(column))
        if text:
            return text
    return None


def build_entry_summary(
    entry: BibEntry,
    source_file: File | None,
    filter_score: Optional[float] = None,
    markdown_file: File | None = None,
    has_translation: bool = False,
) -> LibraryEntrySummary:
    effective_markdown_file = markdown_file or (source_file if source_file and source_file.file_type == "markdown" else None)
    return LibraryEntrySummary(
        id=entry.id,
        title=entry.title,
        authors=_json_list(entry.authors_json),
        year=entry.year,
        doi=entry.doi,
        journal=entry.journal,
        reading_status=entry.reading_status,
        metadata_completeness=entry.metadata_completeness,
        is_pinned=entry.is_pinned,
        source_db=entry.source_db,
        source_file_id=entry.source_file_id,
        source_file_name=source_file.original_name if source_file else None,
        source_file_type=source_file.file_type if source_file else None,
        markdown_source_file_id=entry.markdown_source_file_id or (effective_markdown_file.id if effective_markdown_file else None),
        markdown_source_file_name=effective_markdown_file.original_name if effective_markdown_file else None,
        language=entry.language,
        tags=_json_list(entry.user_tags_json),
        note=entry.user_note,
        filter_score=filter_score,
        has_translation=has_translation,
    )


def sanitize_entry_source_files(
    entry: BibEntry,
    source_file: File | None,
    markdown_file: File | None,
) -> tuple[File | None, File | None, bool]:
    valid_source = source_file if file_record_exists(source_file) else None
    valid_markdown = markdown_file if file_record_exists(markdown_file) else None
    changed = False
    if entry.source_file_id and valid_source is None:
        entry.source_file_id = None
        changed = True
    if entry.markdown_source_file_id and valid_markdown is None:
        entry.markdown_source_file_id = None
        changed = True
    if changed:
        entry.updated_at = utcnow_naive()
    if valid_markdown is None and valid_source is not None and valid_source.file_type == "markdown":
        valid_markdown = valid_source
    return valid_source, valid_markdown, changed


def _candidate_response(candidate) -> FullTextCandidateResponse:
    return FullTextCandidateResponse(
        url=candidate.url,
        source=candidate.source,
        version=candidate.version,
        kind=candidate.kind,
        label=candidate.label,
        confidence=candidate.confidence,
    )


def _safe_pdf_filename(entry: BibEntry, source: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (entry.title or "paper").strip())
    stem = stem.strip("._-")[:90] or "paper"
    source_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", source.strip()).strip("._-")[:32] or "open"
    return f"{stem}_{source_slug}.pdf"


async def _attach_pdf_bytes_to_entry(
    db: AsyncSession,
    user: User,
    entry: BibEntry,
    *,
    filename: str,
    content: bytes,
) -> File:
    md5_hash = hashlib.md5(content).hexdigest()
    existing = (
        await db.execute(
            select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash)
        )
    ).scalar_one_or_none()

    if existing is not None:
        entry.source_file_id = existing.id
        if entry.reading_status == "none":
            entry.reading_status = "has_pdf"
        entry.updated_at = utcnow_naive()
        return existing

    file_id = str(uuid.uuid4())
    final_path, storage_path = build_storage_path(user.id, file_id, ".pdf")
    final_path.write_bytes(content)
    record = File(
        id=file_id,
        owner_user_id=user.id,
        original_name=filename,
        file_type="pdf",
        storage_path=storage_path,
        size_bytes=len(content),
        md5=md5_hash,
        expires_at=compute_expires_at(user),
    )
    db.add(record)
    await db.flush()
    entry.source_file_id = record.id
    if entry.reading_status == "none":
        entry.reading_status = "has_pdf"
    entry.updated_at = utcnow_naive()
    return record


async def get_owned_entry(db: AsyncSession, user: User, entry_id: str) -> BibEntry:
    entry = (
        await db.execute(
            select(BibEntry).where(BibEntry.id == entry_id, BibEntry.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bib entry not found")
    return entry


async def get_owned_ai_comment(db: AsyncSession, user: User, comment_id: str) -> Annotation:
    comment = (
        await db.execute(
            select(Annotation).where(
                Annotation.id == comment_id,
                Annotation.owner_user_id == user.id,
                Annotation.source_type == "library_note",
                Annotation.is_ai_generated == 1,
            )
        )
    ).scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI comment not found")
    return comment


class BatchDeleteRequest(BaseModel):
    entry_ids: list[str] = Field(..., min_length=1, max_length=200)


class LibraryEntryIdsRequest(BaseModel):
    entry_ids: list[str] = Field(default_factory=list)


class BatchTagsRequest(BaseModel):
    entry_ids: list[str] = Field(..., min_length=1, max_length=200)
    add_tags: list[str] = Field(default_factory=list, max_length=20)
    remove_tags: list[str] = Field(default_factory=list, max_length=20)


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        text = str(tag).strip()
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


@router.get("/tags", response_model=list[str])
async def list_tags(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[str]:
    rows = (
        await db.execute(
            select(BibEntry.user_tags_json).where(BibEntry.owner_user_id == user.id)
        )
    ).scalars().all()
    tags: list[str] = []
    seen: set[str] = set()
    for value in rows:
        for tag in _clean_tags(_json_list(value)):
            normalized = tag.casefold()
            if normalized not in seen:
                seen.add(normalized)
                tags.append(tag)
    return sorted(tags, key=str.casefold)


@router.post("/entries/batch-delete")
async def batch_delete_entries(
    body: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    ids = body.entry_ids
    rows = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.id.in_(ids),
                BibEntry.owner_user_id == user.id,
            )
        )
    ).scalars().all()
    found_ids = {r.id for r in rows}
    await db.execute(
        BibReference.__table__.update()
        .where(BibReference.matched_bib_entry_id.in_(found_ids))
        .values(matched_bib_entry_id=None)
    )
    for r in rows:
        await db.delete(r)
    await db.commit()
    return {"deleted": len(found_ids), "not_found": len(ids) - len(found_ids)}


@router.post("/entries/batch-tags")
async def batch_update_tags(
    body: BatchTagsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    add_tags = _clean_tags(body.add_tags)
    remove_tags = set(_clean_tags(body.remove_tags))
    if not add_tags and not remove_tags:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one tag change is required.",
        )

    rows = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.id.in_(body.entry_ids),
                BibEntry.owner_user_id == user.id,
            )
        )
    ).scalars().all()
    changed = 0
    for row in rows:
        original_tags = _clean_tags(_json_list(row.user_tags_json))
        next_tags = [tag for tag in original_tags if tag not in remove_tags]
        for tag in add_tags:
            if tag not in next_tags:
                next_tags.append(tag)
        if next_tags != original_tags:
            row.user_tags_json = json.dumps(next_tags, ensure_ascii=False)
            changed += 1

    await db.commit()
    return {
        "matched": len(rows),
        "changed": changed,
        "not_found": len(body.entry_ids) - len(rows),
    }


@router.get("/entries", response_model=list[LibraryEntrySummary])
async def list_entries(
    search: str = Query(default=""),
    journal: str = Query(default=""),
    tags: str = Query(default=""),
    reading_status: str = Query(default=""),
    pinned_only: bool = Query(default=False),
    sort_by: str = Query(default="updated"),
    sort_order: str = Query(default="desc"),
    entry_ids: str = Query(default=""),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LibraryEntrySummary]:
    ids_list = [eid.strip() for eid in entry_ids.split(",") if eid.strip()]
    return await _list_entries(
        db=db,
        user=user,
        search=search,
        journal=journal,
        tags=_clean_tags(tags.split(",")),
        reading_status=reading_status,
        pinned_only=pinned_only,
        sort_by=sort_by,
        sort_order=sort_order,
        entry_ids=ids_list,
    )


@router.get("/entries/page", response_model=LibraryEntryPageResponse)
async def list_entries_page(
    search: str = Query(default=""),
    journal: str = Query(default=""),
    tags: str = Query(default=""),
    reading_status: str = Query(default=""),
    pinned_only: bool = Query(default=False),
    sort_by: str = Query(default="updated"),
    sort_order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryEntryPageResponse:
    return await _list_entries_page(
        db=db,
        user=user,
        search=search,
        journal=journal,
        tags=_clean_tags(tags.split(",")),
        reading_status=reading_status,
        pinned_only=pinned_only,
        sort_by=sort_by,
        sort_order=sort_order,
        entry_ids=[],
        page=page,
        page_size=page_size,
    )


@router.post("/entries/by-ids", response_model=list[LibraryEntrySummary])
async def list_entries_by_ids(
    request: LibraryEntryIdsRequest,
    search: str = Query(default=""),
    journal: str = Query(default=""),
    tags: str = Query(default=""),
    reading_status: str = Query(default=""),
    pinned_only: bool = Query(default=False),
    sort_by: str = Query(default="updated"),
    sort_order: str = Query(default="desc"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LibraryEntrySummary]:
    entry_ids = [entry_id.strip() for entry_id in request.entry_ids if entry_id.strip()]
    if not entry_ids:
        return []
    return await _list_entries(
        db=db,
        user=user,
        search=search,
        journal=journal,
        tags=_clean_tags(tags.split(",")),
        reading_status=reading_status,
        pinned_only=pinned_only,
        sort_by=sort_by,
        sort_order=sort_order,
        entry_ids=entry_ids,
    )


def _build_entries_stmt(
    *,
    user: User,
    search: str,
    journal: str,
    tags: list[str],
    reading_status: str,
    pinned_only: bool,
    entry_ids: list[str],
):
    score_subq = (
        select(BibFilterLink.bib_entry_id, func.max(BibFilterLink.score).label("max_score"))
        .group_by(BibFilterLink.bib_entry_id)
        .subquery()
    )

    translation_subq = (
        select(JobBibEntry.bib_entry_id, literal("1").label("has_translation"))
        .join(Artifact, Artifact.job_id == JobBibEntry.job_id)
        .where(Artifact.artifact_type == "translation_md")
        .group_by(JobBibEntry.bib_entry_id)
        .subquery()
    )

    stmt = (
        select(BibEntry, File, score_subq.c.max_score, translation_subq.c.has_translation)
        .outerjoin(File, File.id == BibEntry.source_file_id)
        .outerjoin(score_subq, score_subq.c.bib_entry_id == BibEntry.id)
        .outerjoin(translation_subq, translation_subq.c.bib_entry_id == BibEntry.id)
        .where(BibEntry.owner_user_id == user.id)
    )
    if search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                BibEntry.title.ilike(like),
                BibEntry.doi.ilike(like),
                BibEntry.journal.ilike(like),
            )
        )
    if journal.strip():
        stmt = stmt.where(BibEntry.journal.ilike(f"%{journal.strip()}%"))
    if reading_status.strip():
        stmt = stmt.where(BibEntry.reading_status == reading_status.strip())
    if pinned_only:
        stmt = stmt.where(BibEntry.is_pinned == 1)
    if entry_ids:
        stmt = stmt.where(BibEntry.id.in_(entry_ids))
    for tag in tags:
        escaped = tag.replace('"', '\\"')
        stmt = stmt.where(BibEntry.user_tags_json.ilike(f'%"{escaped}"%'))
    return stmt, score_subq


def _apply_entry_sorting(stmt, *, sort_by: str, sort_order: str):
    if sort_by == "score":
        if sort_order == "desc":
            return stmt.order_by(desc(func.coalesce(stmt.selected_columns.max_score, 0)), BibEntry.created_at.desc())
        return stmt.order_by(asc(func.coalesce(stmt.selected_columns.max_score, 0)), BibEntry.created_at.desc())
    if sort_by == "year":
        if sort_order == "desc":
            return stmt.order_by(desc(BibEntry.year), BibEntry.created_at.desc())
        return stmt.order_by(asc(BibEntry.year), BibEntry.created_at.desc())
    if sort_by == "journal":
        if sort_order == "desc":
            return stmt.order_by(desc(func.coalesce(BibEntry.journal, "")), BibEntry.created_at.desc())
        return stmt.order_by(asc(func.coalesce(BibEntry.journal, "")), BibEntry.created_at.desc())
    return stmt.order_by(BibEntry.is_pinned.desc(), BibEntry.updated_at.desc(), BibEntry.created_at.desc())


async def _list_entries(
    *,
    db: AsyncSession,
    user: User,
    search: str,
    journal: str,
    tags: list[str],
    reading_status: str,
    pinned_only: bool,
    sort_by: str,
    sort_order: str,
    entry_ids: list[str],
) -> list[LibraryEntrySummary]:
    stmt, _score_subq = _build_entries_stmt(
        user=user,
        search=search,
        journal=journal,
        tags=tags,
        reading_status=reading_status,
        pinned_only=pinned_only,
        entry_ids=entry_ids,
    )
    stmt = _apply_entry_sorting(stmt, sort_by=sort_by, sort_order=sort_order)

    rows = (await db.execute(stmt)).all()
    summaries: list[LibraryEntrySummary] = []
    changed = False
    for entry, source_file, max_score, has_translation in rows:
        markdown_file = await db.get(File, entry.markdown_source_file_id) if entry.markdown_source_file_id else None
        source_file, markdown_file, repaired = sanitize_entry_source_files(entry, source_file, markdown_file)
        changed = changed or repaired
        summaries.append(build_entry_summary(entry, source_file, max_score, markdown_file, bool(has_translation)))
    if changed:
        await db.commit()
    return summaries


async def _list_entries_page(
    *,
    db: AsyncSession,
    user: User,
    search: str,
    journal: str,
    tags: list[str],
    reading_status: str,
    pinned_only: bool,
    sort_by: str,
    sort_order: str,
    entry_ids: list[str],
    page: int,
    page_size: int,
) -> LibraryEntryPageResponse:
    stmt, _score_subq = _build_entries_stmt(
        user=user,
        search=search,
        journal=journal,
        tags=tags,
        reading_status=reading_status,
        pinned_only=pinned_only,
        entry_ids=entry_ids,
    )
    total = (
        await db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
    ).scalar_one()
    paged_stmt = _apply_entry_sorting(stmt, sort_by=sort_by, sort_order=sort_order).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(paged_stmt)).all()
    items: list[LibraryEntrySummary] = []
    changed = False
    for entry, source_file, max_score, has_translation in rows:
        markdown_file = await db.get(File, entry.markdown_source_file_id) if entry.markdown_source_file_id else None
        source_file, markdown_file, repaired = sanitize_entry_source_files(entry, source_file, markdown_file)
        changed = changed or repaired
        items.append(build_entry_summary(entry, source_file, max_score, markdown_file, bool(has_translation)))
    if changed:
        await db.commit()
    return LibraryEntryPageResponse(
        items=items,
        total=int(total or 0),
        page=page,
        page_size=page_size,
        has_more=page * page_size < int(total or 0),
    )


@router.get("/entries/{entry_id}", response_model=LibraryEntryDetail)
async def get_entry_detail(
    entry_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryEntryDetail:
    entry = await get_owned_entry(db, user, entry_id)
    source_file = await db.get(File, entry.source_file_id) if entry.source_file_id else None
    markdown_file = await db.get(File, entry.markdown_source_file_id) if entry.markdown_source_file_id else None
    source_file, markdown_file, changed = sanitize_entry_source_files(entry, source_file, markdown_file)
    if changed:
        await db.commit()

    timeline_rows = (
        await db.execute(
            select(Job, Artifact)
            .join(JobBibEntry, JobBibEntry.job_id == Job.id)
            .outerjoin(Artifact, Artifact.job_id == Job.id)
            .where(JobBibEntry.bib_entry_id == entry.id, Job.owner_user_id == user.id)
            .order_by(Job.created_at.desc(), Artifact.sort_order.asc(), Artifact.id.asc())
        )
    ).all()

    grouped: dict[str, LibraryTimelineItem] = {}
    for job, artifact in timeline_rows:
        item = grouped.get(job.id)
        if item is None:
            item = LibraryTimelineItem(
                job_id=job.id,
                job_type=job.job_type,
                status=job.status,
                created_at=_dt(job.created_at),
                finished_at=_dt(job.finished_at),
                artifacts=[],
            )
            grouped[job.id] = item
        if artifact is not None:
            item.artifacts.append(
                LibraryArtifactResponse(
                    id=artifact.id,
                    filename=artifact.filename,
                    artifact_type=artifact.artifact_type,
                    storage_path=artifact.storage_path,
                    created_at=_dt(artifact.created_at),
                )
            )

    filter_rows = (
        await db.execute(
            select(BibFilterLink, Job, Artifact)
            .join(Job, Job.id == BibFilterLink.filter_job_id)
            .outerjoin(
                Artifact,
                (Artifact.job_id == Job.id) & (Artifact.artifact_type == "filter_excel"),
            )
            .where(BibFilterLink.bib_entry_id == entry.id, Job.owner_user_id == user.id)
            .order_by(Job.created_at.desc(), BibFilterLink.id.desc())
        )
    ).all()

    filter_evaluations: list[LibraryFilterEvaluation] = []
    for link, job, artifact in filter_rows:
        filter_evaluations.append(
            LibraryFilterEvaluation(
                filter_job_id=job.id,
                passed=link.passed,
                score=link.score,
                reason=link.reason,
                abstract_translation=entry.abstract_cn or _load_abstract_translation_from_artifact(entry, artifact),
                created_at=_dt(link.created_at),
            )
        )

    ai_comment_rows = (
        await db.execute(
            select(Annotation)
            .where(
                Annotation.owner_user_id == user.id,
                Annotation.bib_entry_id == entry.id,
                Annotation.source_type == "library_note",
                Annotation.is_ai_generated == 1,
            )
            .order_by(Annotation.created_at.desc(), Annotation.id.desc())
        )
    ).scalars().all()
    ai_comments = [
        LibraryAiComment(
            id=annotation.id,
            source_id=annotation.source_id,
            question=annotation.selected_text,
            note=annotation.note,
            created_at=_dt(annotation.created_at),
            updated_at=_dt(annotation.updated_at),
        )
        for annotation in ai_comment_rows
    ]

    summary = build_entry_summary(entry, source_file, markdown_file=markdown_file)

    attachment_rows = (
        await db.execute(
            select(BibAttachment, File)
            .join(File, File.id == BibAttachment.file_id)
            .where(BibAttachment.bib_entry_id == entry.id, BibAttachment.owner_user_id == user.id)
            .order_by(BibAttachment.sort_order.asc(), BibAttachment.created_at.asc())
        )
    ).all()
    attachments = [
        AttachmentSummary(
            id=att.id,
            file_id=att.file_id,
            label=att.label,
            sort_order=att.sort_order,
            file_name=f.original_name,
            file_size=f.size_bytes,
            created_at=_dt(att.created_at),
        )
        for att, f in attachment_rows
    ]

    return LibraryEntryDetail(
        **summary.model_dump(),
        abstract=entry.abstract,
        abstract_cn=entry.abstract_cn,
        keywords=_json_list(entry.keywords_json),
        timeline=list(grouped.values()),
        filter_evaluations=filter_evaluations,
        ai_comments=ai_comments,
        attachments=attachments,
    )


@router.patch("/entries/{entry_id}", response_model=LibraryEntryDetail)
async def update_entry(
    entry_id: str,
    request: LibraryEntryUpdateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryEntryDetail:
    entry = await get_owned_entry(db, user, entry_id)

    if request.title is not None:
        entry.title = request.title.strip()
    if request.authors is not None:
        entry.authors_json = json.dumps(request.authors, ensure_ascii=False)
    if request.year is not None:
        entry.year = request.year
    if request.doi is not None:
        entry.doi = request.doi.strip() or None
    if request.journal is not None:
        entry.journal = request.journal.strip() or None
    if request.abstract is not None:
        entry.abstract = request.abstract.strip() or None
    if request.keywords is not None:
        entry.keywords_json = json.dumps(request.keywords, ensure_ascii=False)
    if request.tags is not None:
        entry.user_tags_json = json.dumps(request.tags, ensure_ascii=False)
    if request.note is not None:
        entry.user_note = request.note.strip() or None
    if request.is_pinned is not None:
        entry.is_pinned = request.is_pinned
    if request.language is not None:
        entry.language = _clean_language(request.language)

    await db.commit()
    return await get_entry_detail(entry_id, user=user, db=db)


@router.post("/entries/{entry_id}/markdown", response_model=LibraryEntryDetail)
async def upload_entry_markdown(
    entry_id: str,
    file: UploadFile = FastAPIFile(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryEntryDetail:
    entry = await get_owned_entry(db, user, entry_id)
    original_name = (file.filename or "").strip()
    if not original_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少文件名。")
    file_ext = Path(original_name).suffix.lower()
    if file_ext not in {".md", ".markdown"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传 Markdown 文件。")

    user_dir = get_user_upload_dir(user.id)
    temp_path = user_dir / f".{uuid.uuid4()}.uploading"
    final_path = None
    try:
        md5_hash, size_bytes, sample = await persist_upload_to_temp(file, temp_path)
        if detect_file_type(original_name, sample) != "markdown":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传 Markdown 文件。")

        record = (
            await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
        ).scalar_one_or_none()
        if record is not None and not file_record_exists(record):
            final_path, storage_path = build_storage_path(user.id, record.id, file_ext)
            shutil.move(str(temp_path), str(final_path))
            record.original_name = original_name
            record.file_type = "markdown"
            record.storage_path = storage_path
            record.size_bytes = size_bytes
            record.expires_at = compute_expires_at(user)
        elif record is None:
            file_id = str(uuid.uuid4())
            final_path, storage_path = build_storage_path(user.id, file_id, file_ext)
            shutil.move(str(temp_path), str(final_path))
            record = File(
                id=file_id,
                owner_user_id=user.id,
                original_name=original_name,
                file_type="markdown",
                storage_path=storage_path,
                size_bytes=size_bytes,
                md5=md5_hash,
                expires_at=compute_expires_at(user),
            )
            db.add(record)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                if final_path and final_path.exists():
                    final_path.unlink()
                record = (
                    await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
                ).scalar_one_or_none()
                if record is None:
                    raise
        else:
            if temp_path.exists():
                temp_path.unlink()

        entry.markdown_source_file_id = record.id
        if not entry.source_file_id:
            entry.source_file_id = record.id
        if entry.reading_status == "none":
            entry.reading_status = "has_pdf"
        entry.updated_at = utcnow_naive()
        await db.commit()
        return await get_entry_detail(entry_id, user=user, db=db)
    except HTTPException:
        if temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        await file.close()


@router.post("/entries/{entry_id}/attachments", response_model=list[AttachmentSummary])
async def upload_attachment(
    entry_id: str,
    file: UploadFile = FastAPIFile(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AttachmentSummary]:
    entry = await get_owned_entry(db, user, entry_id)
    original_name = (file.filename or "").strip()
    if not original_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少文件名。")
    file_ext = Path(original_name).suffix.lower()
    if file_ext not in {".md", ".markdown"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="附件仅支持 Markdown 文件。")

    user_dir = get_user_upload_dir(user.id)
    temp_path = user_dir / f".{uuid.uuid4()}.uploading"
    final_path = None
    try:
        md5_hash, size_bytes, sample = await persist_upload_to_temp(file, temp_path)
        if detect_file_type(original_name, sample) != "markdown":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请上传 Markdown 文件。")

        record = (
            await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
        ).scalar_one_or_none()
        if record is None:
            file_id = str(uuid.uuid4())
            final_path, storage_path = build_storage_path(user.id, file_id, file_ext)
            shutil.move(str(temp_path), str(final_path))
            record = File(
                id=file_id,
                owner_user_id=user.id,
                original_name=original_name,
                file_type="markdown",
                storage_path=storage_path,
                size_bytes=size_bytes,
                md5=md5_hash,
                expires_at=compute_expires_at(user),
            )
            db.add(record)
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                if final_path and final_path.exists():
                    final_path.unlink()
                record = (
                    await db.execute(select(File).where(File.owner_user_id == user.id, File.md5 == md5_hash))
                ).scalar_one_or_none()
                if record is None:
                    raise
        else:
            if temp_path.exists():
                temp_path.unlink()

        existing_link = (
            await db.execute(
                select(BibAttachment).where(
                    BibAttachment.bib_entry_id == entry.id,
                    BibAttachment.file_id == record.id,
                )
            )
        ).scalar_one_or_none()
        if existing_link is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该文件已作为附件挂载。")

        max_order = (
            await db.execute(
                select(func.coalesce(func.max(BibAttachment.sort_order), -1))
                .where(BibAttachment.bib_entry_id == entry.id)
            )
        ).scalar_one()

        att = BibAttachment(
            id=str(uuid.uuid4()),
            bib_entry_id=entry.id,
            file_id=record.id,
            label=Path(original_name).stem,
            sort_order=max_order + 1,
            owner_user_id=user.id,
            expires_at=compute_expires_at(user),
        )
        db.add(att)
        await db.commit()
    except HTTPException:
        if temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        await file.close()

    return (await _list_attachments_inner(db, user, entry))


async def _list_attachments_inner(db: AsyncSession, user: User, entry: BibEntry) -> list[AttachmentSummary]:
    rows = (
        await db.execute(
            select(BibAttachment, File)
            .join(File, File.id == BibAttachment.file_id)
            .where(BibAttachment.bib_entry_id == entry.id, BibAttachment.owner_user_id == user.id)
            .order_by(BibAttachment.sort_order.asc(), BibAttachment.created_at.asc())
        )
    ).all()
    return [
        AttachmentSummary(
            id=att.id,
            file_id=att.file_id,
            label=att.label,
            sort_order=att.sort_order,
            file_name=f.original_name,
            file_size=f.size_bytes,
            created_at=_dt(att.created_at),
        )
        for att, f in rows
    ]


@router.get("/entries/{entry_id}/attachments", response_model=list[AttachmentSummary])
async def list_attachments(
    entry_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AttachmentSummary]:
    entry = await get_owned_entry(db, user, entry_id)
    return await _list_attachments_inner(db, user, entry)


@router.patch("/entries/{entry_id}/attachments/{attachment_id}", response_model=AttachmentSummary)
async def update_attachment(
    entry_id: str,
    attachment_id: str,
    request: AttachmentUpdateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> AttachmentSummary:
    entry = await get_owned_entry(db, user, entry_id)
    att = (
        await db.execute(
            select(BibAttachment).where(
                BibAttachment.id == attachment_id,
                BibAttachment.bib_entry_id == entry.id,
                BibAttachment.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在。")
    if request.label is not None:
        att.label = request.label.strip()
    if request.sort_order is not None:
        att.sort_order = request.sort_order
    await db.commit()
    f = await db.get(File, att.file_id)
    return AttachmentSummary(
        id=att.id,
        file_id=att.file_id,
        label=att.label,
        sort_order=att.sort_order,
        file_name=f.original_name if f else None,
        file_size=f.size_bytes if f else None,
        created_at=_dt(att.created_at),
    )


@router.delete("/entries/{entry_id}/attachments/{attachment_id}")
async def delete_attachment(
    entry_id: str,
    attachment_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await get_owned_entry(db, user, entry_id)
    att = (
        await db.execute(
            select(BibAttachment).where(
                BibAttachment.id == attachment_id,
                BibAttachment.bib_entry_id == entry.id,
                BibAttachment.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if att is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="附件不存在。")
    await db.delete(att)
    await db.commit()
    return {"ok": True}



@router.post("/entries/{entry_id}/fulltext-search", response_model=FullTextLookupResponse)
async def search_entry_fulltext(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> FullTextLookupResponse:
    entry = await get_owned_entry(db, user, entry_id)
    authors = _json_list(entry.authors_json)
    lookup = await lookup_fulltext(
        title=entry.title,
        doi=entry.doi,
        authors=authors,
        year=entry.year,
    )

    errors: list[str] = []
    for candidate in lookup.pdf_candidates[:5]:
        try:
            content, final_url = await download_pdf_candidate(candidate.url)
            record = await _attach_pdf_bytes_to_entry(
                db,
                user,
                entry,
                filename=_safe_pdf_filename(entry, candidate.source),
                content=content,
            )
            await db.commit()
            return FullTextLookupResponse(
                status="attached",
                message=f"已找到并挂载 {candidate.label}。",
                attached_file_id=record.id,
                attached_file_name=record.original_name,
                attached_source_url=final_url,
                doi=lookup.doi,
                pdf_candidates=[_candidate_response(item) for item in lookup.pdf_candidates],
                landing_pages=[_candidate_response(item) for item in lookup.landing_pages],
                working_paper_searches=[_candidate_response(item) for item in lookup.working_paper_searches],
                errors=errors,
            )
        except Exception as exc:
            errors.append(f"{candidate.source}: {exc}")

    status_text = "landing_only" if lookup.landing_pages else "search_only"
    message = (
        "未能自动挂载 PDF，已返回 DOI/开放访问页面和 working paper 检索入口。"
        if status_text == "landing_only"
        else "未能自动挂载 PDF，已返回 working paper 检索入口。"
    )
    return FullTextLookupResponse(
        status=status_text,
        message=message,
        doi=lookup.doi,
        pdf_candidates=[_candidate_response(item) for item in lookup.pdf_candidates],
        landing_pages=[_candidate_response(item) for item in lookup.landing_pages],
        working_paper_searches=[_candidate_response(item) for item in lookup.working_paper_searches],
        errors=errors,
    )


@router.get("/entries/{entry_id}/reader", response_model=ReaderResponse)
async def get_entry_reader(
    entry_id: str,
    view: str = Query(default="original"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ReaderResponse:
    entry = await get_owned_entry(db, user, entry_id)
    source_file = await db.get(File, entry.source_file_id) if entry.source_file_id else None
    markdown_file = await db.get(File, entry.markdown_source_file_id) if entry.markdown_source_file_id else None
    source_file, markdown_file, changed = sanitize_entry_source_files(entry, source_file, markdown_file)
    if changed:
        await db.commit()

    translation_row = (
        await db.execute(
            select(Artifact)
            .join(Job, Job.id == Artifact.job_id)
            .join(JobBibEntry, JobBibEntry.job_id == Job.id)
            .where(
                JobBibEntry.bib_entry_id == entry.id,
                Job.owner_user_id == user.id,
                Artifact.owner_user_id == user.id,
                Artifact.artifact_type == "translation_md",
                Job.status == "success",
            )
            .order_by(Artifact.created_at.desc(), Artifact.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    attachment_rows = (
        await db.execute(
            select(BibAttachment, File)
            .join(File, File.id == BibAttachment.file_id)
            .where(BibAttachment.bib_entry_id == entry.id, BibAttachment.owner_user_id == user.id)
            .order_by(BibAttachment.sort_order.asc(), BibAttachment.created_at.asc())
        )
    ).all()

    versions = [
        ReaderVersion(version="original", label="原文", available=markdown_file is not None),
        ReaderVersion(version="translated", label="译文", available=translation_row is not None),
    ]
    for att, att_file in attachment_rows:
        versions.append(
            ReaderVersion(version=f"attachment:{att.file_id}", label=att.label, available=True)
        )

    attachment_file_map: dict[str, tuple[BibAttachment, File]] = {
        att.file_id: (att, f) for att, f in attachment_rows
    }

    current = view
    is_attachment_view = current.startswith("attachment:")

    if is_attachment_view:
        att_file_id = current.split(":", 1)[1]
        if att_file_id not in attachment_file_map:
            if markdown_file is not None:
                current = "original"
                is_attachment_view = False
            elif translation_row is not None:
                current = "translated"
                is_attachment_view = False
            else:
                raise HTTPException(status_code=404, detail="请求的附件不存在。")
    else:
        if current == "translated" and translation_row is None:
            current = "original"
        if current == "original" and markdown_file is None and translation_row is not None:
            current = "translated"
        if current == "original" and markdown_file is None and not attachment_rows:
            raise HTTPException(status_code=404, detail="当前文献尚未绑定 Markdown 原文。")
        if current == "original" and markdown_file is None and attachment_rows:
            first_att, first_f = attachment_rows[0]
            current = f"attachment:{first_att.file_id}"
            is_attachment_view = True

    if is_attachment_view:
        att_file_id = current.split(":", 1)[1]
        _, att_file = attachment_file_map[att_file_id]
        markdown = read_markdown_file(att_file.storage_path)
        source_markdown_file_id = att_file.id
        source_translation_artifact_id = None
    elif current == "translated":
        markdown = read_artifact_markdown(translation_row.storage_path) if translation_row else ""
        source_translation_artifact_id = translation_row.id if translation_row else None
        source_markdown_file_id = None
    else:
        if markdown_file is None:
            raise HTTPException(status_code=404, detail="当前文献原文文件已丢失，请重新上传 Markdown 原文。")
        markdown = read_markdown_file(markdown_file.storage_path)
        source_translation_artifact_id = None
        source_markdown_file_id = markdown_file.id

    card_rows = (
        await db.execute(
            select(CardNote)
            .where(CardNote.owner_user_id == user.id, CardNote.source_bib_entry_id == entry.id)
            .order_by(CardNote.created_at.desc(), CardNote.id.desc())
        )
    ).scalars().all()
    cards = [
        ReaderCardSummary(
            id=card.id,
            title=card.title,
            summary=card.summary,
            tags=json_list(card.tags_json),
            source_version=card.source_version,
            created_at=_dt(card.created_at),
        )
        for card in card_rows
    ]

    outgoing_refs = (
        await db.execute(
            select(BibReference)
            .where(BibReference.owner_user_id == user.id, BibReference.source_bib_entry_id == entry.id)
            .order_by(BibReference.reference_order.asc())
        )
    ).scalars().all()
    incoming_refs = (
        await db.execute(
            select(BibReference, BibEntry)
            .join(BibEntry, BibEntry.id == BibReference.source_bib_entry_id)
            .where(
                BibReference.owner_user_id == user.id,
                BibReference.matched_bib_entry_id == entry.id,
            )
            .order_by(BibReference.updated_at.desc())
        )
    ).all()

    summary = build_entry_summary(entry, source_file, markdown_file=markdown_file)
    return ReaderResponse(
        entry={
            **summary.model_dump(),
            "abstract": entry.abstract,
            "keywords": json_list(entry.keywords_json),
            "volume": entry.volume,
            "issue": entry.issue,
            "pages": entry.pages,
        },
        current_version=current,
        versions=versions,
        markdown=strip_frontmatter(markdown),
        source_markdown_file_id=source_markdown_file_id,
        source_translation_artifact_id=source_translation_artifact_id,
        cards=cards,
        citations={
            "outgoing": [
                {
                    "id": ref.id,
                    "order": ref.reference_order,
                    "title": ref.title,
                    "raw_text": ref.raw_text,
                    "matched_bib_entry_id": ref.matched_bib_entry_id,
                }
                for ref in outgoing_refs
            ],
            "incoming": [
                {
                    "reference_id": ref.id,
                    "source_bib_entry_id": source.id,
                    "source_title": source.title,
                    "raw_text": ref.raw_text,
                }
                for ref, source in incoming_refs
            ],
        },
    )


@router.patch("/ai-comments/{comment_id}", response_model=LibraryAiComment)
async def update_ai_comment(
    comment_id: str,
    request: LibraryAiCommentUpdateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryAiComment:
    comment = await get_owned_ai_comment(db, user, comment_id)
    note = request.note.strip()
    if not note:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="AI comment cannot be empty.",
        )
    comment.note = note
    comment.updated_at = utcnow_naive()
    await db.commit()
    await db.refresh(comment)
    return LibraryAiComment(
        id=comment.id,
        source_id=comment.source_id,
        question=comment.selected_text,
        note=comment.note,
        created_at=_dt(comment.created_at),
        updated_at=_dt(comment.updated_at),
    )


@router.delete("/ai-comments/{comment_id}")
async def delete_ai_comment(
    comment_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    comment = await get_owned_ai_comment(db, user, comment_id)
    await db.delete(comment)
    await db.commit()
    return {"ok": True}


@router.post("/entries/batch-translate-abstracts")
async def batch_translate_abstracts(
    req: BatchTranslateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        api_key = validate_deepseek_key(req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job = Job(
        id=str(uuid.uuid4()),
        owner_user_id=user.id,
        job_type="translate_abstracts",
        status="pending",
        progress=0,
        current_stage="准备翻译...",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    in_memory_status = {"status": "pending"}

    def cancel_check():
        return in_memory_status.get("status") == "cancelled"

    thread = threading.Thread(
        target=run_batch_translate,
        args=(job.id, user.id, req.entry_ids, api_key),
        daemon=True,
    )
    thread.start()

    return {"job_id": job.id}


@router.get("/translate-job/{job_id}/status")
async def get_translate_job_status(
    job_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.owner_user_id == user.id))
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = None
    if job.params_json:
        try:
            result = json.loads(job.params_json)
        except Exception:
            pass

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "current_stage": job.current_stage,
        "error": job.error_msg,
        "result": result,
    }


# ============================================================
# Online Metadata Matching Endpoints
# ============================================================


class OnlineMatchResponse(BaseModel):
    candidates: list[dict]
    extracted_metadata: dict
    high_confidence_count: int
    medium_confidence_count: int


class ApplyMatchRequest(BaseModel):
    candidate: dict


async def _merge_duplicate_bib_entry(db: AsyncSession, winner: BibEntry, loser: BibEntry) -> list[str]:
    if not winner.doi and loser.doi:
        winner.doi = loser.doi
    if not winner.journal and loser.journal:
        winner.journal = loser.journal
    if not winner.abstract and loser.abstract:
        winner.abstract = loser.abstract
    if not winner.year and loser.year:
        winner.year = loser.year
    if not winner.volume and loser.volume:
        winner.volume = loser.volume
    if not winner.issue and loser.issue:
        winner.issue = loser.issue
    if not winner.pages and loser.pages:
        winner.pages = loser.pages
    if not winner.venue_type and loser.venue_type:
        winner.venue_type = loser.venue_type
    if not winner.citation_count and loser.citation_count:
        winner.citation_count = loser.citation_count

    winner_authors = json.loads(winner.authors_json) if winner.authors_json else []
    loser_authors = json.loads(loser.authors_json) if loser.authors_json else []
    if not winner_authors and loser_authors:
        winner.authors_json = json.dumps(loser_authors, ensure_ascii=False)

    winner_kw = json.loads(winner.keywords_json) if winner.keywords_json else []
    loser_kw = json.loads(loser.keywords_json) if loser.keywords_json else []
    if not winner_kw and loser_kw:
        winner.keywords_json = json.dumps(loser_kw, ensure_ascii=False)

    if not winner.source_file_id and loser.source_file_id:
        winner.source_file_id = loser.source_file_id

    better_status = {"read": 4, "reading": 3, "has_pdf": 2, "none": 1}
    if better_status.get(loser.reading_status, 0) > better_status.get(winner.reading_status, 0):
        winner.reading_status = loser.reading_status

    link_rows = (
        await db.execute(
            select(BibFilterLink).where(BibFilterLink.bib_entry_id == loser.id)
        )
    ).scalars().all()
    for link in link_rows:
        existing = (
            await db.execute(
                select(BibFilterLink).where(
                    BibFilterLink.bib_entry_id == winner.id,
                    BibFilterLink.filter_job_id == link.filter_job_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            link.bib_entry_id = winner.id
        else:
            await db.delete(link)

    jbe_rows = (
        await db.execute(
            select(JobBibEntry).where(JobBibEntry.bib_entry_id == loser.id)
        )
    ).scalars().all()
    for jbe in jbe_rows:
        existing_jbe = (
            await db.execute(
                select(JobBibEntry).where(
                    JobBibEntry.job_id == jbe.job_id,
                    JobBibEntry.bib_entry_id == winner.id,
                    JobBibEntry.role == jbe.role,
                )
            )
        ).scalar_one_or_none()
        if existing_jbe is None:
            jbe.bib_entry_id = winner.id
        else:
            await db.delete(jbe)

    ri_rows = (
        await db.execute(
            select(ReadingItem).where(
                ReadingItem.bib_entry_id == loser.id,
                ReadingItem.owner_user_id == winner.owner_user_id,
            )
        )
    ).scalars().all()
    for ri in ri_rows:
        ri.bib_entry_id = winner.id

    await db.delete(loser)
    return ["merged_with_local"]


@router.post("/entries/{entry_id}/match-online", response_model=OnlineMatchResponse)
async def match_online(
    entry_id: str,
    request: dict = {},
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> OnlineMatchResponse:
    entry = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.id == entry_id,
                BibEntry.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if entry is None:
        raise HTTPException(status_code=404, detail="文献不存在。")

    api_key = request.get("api_key")
    try:
        api_key = validate_deepseek_key(api_key)
    except ValueError:
        api_key = None

    extracted = {
        "title": entry.title,
        "authors": json.loads(entry.authors_json) if entry.authors_json else [],
        "year": entry.year,
        "doi": entry.doi,
        "journal": entry.journal,
        "language": None,
    }

    if entry.source_file_id:
        file_record = await db.get(File, entry.source_file_id)
        if file_record:
            file_path = resolve_storage_path(file_record.storage_path)
            if file_path.exists() and file_path.suffix.lower() == ".pdf":
                front_matter = extract_front_matter(str(file_path))
                if front_matter.get("page_1_full"):
                    llm_metadata = extract_metadata_with_llm(
                        front_matter,
                        file_record.original_name,
                        api_key=api_key,
                    )
                    for key in ["title", "authors", "year", "doi", "journal", "language"]:
                        if not extracted.get(key) and llm_metadata.get(key):
                            extracted[key] = llm_metadata[key]
                    if not extracted.get("doi") and front_matter.get("doi_candidates"):
                        extracted["doi"] = front_matter["doi_candidates"][0]

    candidates: list[CandidateMetadata] = []

    entry_title = (extracted.get("title") or "").strip()
    entry_doi = normalize_doi(extracted.get("doi"))
    title_words = [w for w in re.sub(r"[^\w]+", " ", entry_title.lower()).split() if len(w) >= 2]

    local_stmt = select(BibEntry).where(
        BibEntry.owner_user_id == user.id,
        BibEntry.id != entry.id,
    )

    if entry_doi:
        local_stmt = local_stmt.where(
            or_(BibEntry.doi == entry.doi, BibEntry.title.ilike(f"%{title_words[0]}%"))
            if title_words else BibEntry.doi == entry.doi
        )
    elif title_words:
        local_stmt = local_stmt.where(BibEntry.title.ilike(f"%{title_words[0]}%"))
    else:
        local_stmt = local_stmt.where(BibEntry.metadata_completeness == "full")

    local_rows = (await db.execute(local_stmt)).scalars().all()

    for other in local_rows:
        other_authors = json.loads(other.authors_json) if other.authors_json else []
        existing = {
            "title": other.title,
            "authors": other_authors,
            "year": other.year,
            "doi": other.doi,
            "journal": other.journal,
            "language": None,
        }
        local_score = compute_metadata_match_score(extracted, existing)
        if local_score >= 0.78:
            candidates.append(CandidateMetadata(
                title=other.title,
                authors=other_authors,
                year=other.year,
                journal=other.journal,
                doi=other.doi,
                volume=other.volume,
                issue=other.issue,
                pages=other.pages,
                source="local",
                score=local_score,
            ))

    online_dedup = {normalize_doi(c.doi) for c in candidates if c.doi}

    if extracted.get("doi") and not any(c.source == "local" and c.score >= 0.92 for c in candidates):
        crossref = CrossrefSource()
        openalex = OpenAlexSource()

        doi_result_crossref = await crossref.search_by_doi(extracted["doi"])
        if doi_result_crossref and normalize_doi(doi_result_crossref.doi) not in online_dedup:
            candidates.append(doi_result_crossref)
            online_dedup.add(normalize_doi(doi_result_crossref.doi))

        doi_result_openalex = await openalex.search_by_doi(extracted["doi"])
        if doi_result_openalex and normalize_doi(doi_result_openalex.doi) not in online_dedup:
            candidates.append(doi_result_openalex)
            online_dedup.add(normalize_doi(doi_result_openalex.doi))

    has_local_high = any(c.source == "local" and c.score >= 0.92 for c in candidates)
    if not has_local_high and extracted.get("title"):
        crossref = CrossrefSource()
        openalex = OpenAlexSource()

        title_results_crossref = await crossref.search_by_metadata(
            extracted["title"],
            extracted.get("authors"),
            extracted.get("year"),
            max_results=3,
        )
        candidates.extend(title_results_crossref)

        title_results_openalex = await openalex.search_by_metadata(
            extracted["title"],
            extracted.get("authors"),
            extracted.get("year"),
            max_results=3,
        )
        candidates.extend(title_results_openalex)

    scored = score_candidates(extracted, candidates)

    visible = [c for c in scored if c.score >= 0.78]

    high_count = sum(1 for c in visible if classify_confidence(c.score) == "high")
    medium_count = sum(1 for c in visible if classify_confidence(c.score) == "medium")

    return OnlineMatchResponse(
        candidates=[c.to_dict() for c in visible],
        extracted_metadata=extracted,
        high_confidence_count=high_count,
        medium_confidence_count=medium_count,
    )


@router.post("/entries/{entry_id}/apply-match")
async def apply_match(
    entry_id: str,
    request: ApplyMatchRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    entry = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.id == entry_id,
                BibEntry.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if entry is None:
        raise HTTPException(status_code=404, detail="文献不存在。")

    c = request.candidate
    candidate_source = c.get("source", "unknown")

    extracted = {
        "title": entry.title,
        "authors": json.loads(entry.authors_json) if entry.authors_json else [],
        "year": entry.year,
        "doi": entry.doi,
        "journal": entry.journal,
        "volume": entry.volume,
        "issue": entry.issue,
        "pages": entry.pages,
        "language": None,
    }

    if candidate_source == "local":
        other_entry = (
            await db.execute(
                select(BibEntry).where(
                    BibEntry.owner_user_id == user.id,
                    BibEntry.id != entry.id,
                    BibEntry.title == c.get("title", ""),
                ).limit(1)
            )
        ).scalar_one_or_none()

        if other_entry is None:
            raise HTTPException(status_code=400, detail="本地候选文献不存在。")

        updated_fields = await _merge_duplicate_bib_entry(db, entry, other_entry)
    else:
        candidate = CandidateMetadata(
            title=c.get("title", ""),
            authors=c.get("authors", []),
            year=c.get("year"),
            journal=c.get("journal"),
            doi=c.get("doi"),
            volume=c.get("volume"),
            issue=c.get("issue"),
            pages=c.get("pages"),
            source=candidate_source,
            score=c.get("score", 0.0),
        )
        updates = apply_high_confidence_match(extracted, candidate)

        for field, value in updates.items():
            if field == "authors":
                setattr(entry, "authors_json", json.dumps(value, ensure_ascii=False))
            elif field in ("doi", "journal", "volume", "issue", "pages", "year"):
                setattr(entry, field, value)

        updated_fields = list(updates.keys())

    from db.utils import compute_dedup_key
    new_doi = entry.doi
    new_title = entry.title
    new_authors = json.loads(entry.authors_json) if entry.authors_json else []
    new_year = entry.year
    new_dedup_key = compute_dedup_key(
        normalize_doi(new_doi) or new_doi,
        new_title,
        new_authors,
        new_year,
    )
    duplicate_entry = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == user.id,
                BibEntry.id != entry.id,
                BibEntry.dedup_key == new_dedup_key,
            )
        )
    ).scalar_one_or_none()
    if duplicate_entry is not None:
        updated_fields = await _merge_duplicate_bib_entry(db, entry, duplicate_entry)
        await db.flush()
    entry.dedup_key = new_dedup_key

    mc_title = entry.title
    mc_authors = json.loads(entry.authors_json) if entry.authors_json else []
    mc_year = entry.year
    mc_doi = entry.doi
    mc_journal = entry.journal
    mc_abstract = entry.abstract
    has_title = bool(mc_title.strip())
    has_authors = bool(mc_authors)
    has_year = mc_year is not None
    has_doi = bool((mc_doi or "").strip())
    has_journal = bool((mc_journal or "").strip())
    has_abstract = bool((mc_abstract or "").strip())
    if has_title and has_authors and has_year and has_doi and has_journal and has_abstract:
        entry.metadata_completeness = "full"
    elif has_title and has_authors:
        entry.metadata_completeness = "partial"
    else:
        entry.metadata_completeness = "minimal"

    await db.commit()
    return {"message": "Match applied successfully.", "updated_fields": updated_fields}


@router.post("/entries/{entry_id}/wos-search")
async def wos_search(
    entry_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Use Playwright to search the entry title on Web of Science and return the result URL."""
    entry = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.id == entry_id,
                BibEntry.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="文献不存在。")

    if not entry.title or not entry.title.strip():
        raise HTTPException(status_code=400, detail="文献标题为空，无法搜索。")

    from services.wos_search import search_wos_by_title

    try:
        url = await search_wos_by_title(entry.title)
    except Exception as exc:
        logger.exception("WoS search failed for entry %s", entry_id)
        raise HTTPException(status_code=502, detail=f"WOS 搜索失败：{exc}") from exc

    return {"url": url}
