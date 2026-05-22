"""Library router for bib-entry centric browsing and editing."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import get_db
from db.models import Annotation, Artifact, BibEntry, BibFilterLink, BibReference, File, Job, JobBibEntry, ReadingItem, User
from db.utils import title_match_score, normalize_doi, compute_metadata_match_score
from result_storage import resolve_result_path
from services.crossref_source import CrossrefSource
from services.metadata_match_service import apply_high_confidence_match, classify_confidence, score_candidates
from services.metadata_sources import CandidateMetadata
from services.openalex_source import OpenAlexSource
from services.pdf_metadata_extract import extract_front_matter
from services.pdf_metadata_llm import extract_metadata_with_llm
from upload_storage import resolve_storage_path
from backend.utils.api_key import validate_deepseek_key

router = APIRouter()


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
    language: Optional[str]
    tags: list[str]
    note: Optional[str]
    filter_score: Optional[float] = None


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
    keywords: list[str]
    timeline: list[LibraryTimelineItem]
    filter_evaluations: list[LibraryFilterEvaluation]
    ai_comments: list[LibraryAiComment]


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


def build_entry_summary(entry: BibEntry, source_file: File | None, filter_score: Optional[float] = None) -> LibraryEntrySummary:
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
        language=entry.language,
        tags=_json_list(entry.user_tags_json),
        note=entry.user_note,
        filter_score=filter_score,
    )


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
    score_subq = (
        select(BibFilterLink.bib_entry_id, func.max(BibFilterLink.score).label("max_score"))
        .group_by(BibFilterLink.bib_entry_id)
        .subquery()
    )

    stmt = (
        select(BibEntry, File, score_subq.c.max_score)
        .outerjoin(File, File.id == BibEntry.source_file_id)
        .outerjoin(score_subq, score_subq.c.bib_entry_id == BibEntry.id)
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

    if sort_by == "score":
        if sort_order == "desc":
            stmt = stmt.order_by(desc(func.coalesce(score_subq.c.max_score, 0)), BibEntry.created_at.desc())
        else:
            stmt = stmt.order_by(asc(func.coalesce(score_subq.c.max_score, 0)), BibEntry.created_at.desc())
    elif sort_by == "year":
        if sort_order == "desc":
            stmt = stmt.order_by(desc(BibEntry.year), BibEntry.created_at.desc())
        else:
            stmt = stmt.order_by(asc(BibEntry.year), BibEntry.created_at.desc())
    elif sort_by == "journal":
        if sort_order == "desc":
            stmt = stmt.order_by(desc(func.coalesce(BibEntry.journal, "")), BibEntry.created_at.desc())
        else:
            stmt = stmt.order_by(asc(func.coalesce(BibEntry.journal, "")), BibEntry.created_at.desc())
    else:
        stmt = stmt.order_by(BibEntry.is_pinned.desc(), BibEntry.updated_at.desc(), BibEntry.created_at.desc())

    rows = (await db.execute(stmt)).all()
    summaries = [build_entry_summary(entry, source_file, max_score) for entry, source_file, max_score in rows]
    if tags:
        expected_tags = set(tags)
        summaries = [summary for summary in summaries if expected_tags.issubset(set(summary.tags))]
    return summaries


@router.get("/entries/{entry_id}", response_model=LibraryEntryDetail)
async def get_entry_detail(
    entry_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> LibraryEntryDetail:
    entry = await get_owned_entry(db, user, entry_id)
    source_file = await db.get(File, entry.source_file_id) if entry.source_file_id else None

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
                abstract_translation=_load_abstract_translation_from_artifact(entry, artifact),
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

    summary = build_entry_summary(entry, source_file)
    return LibraryEntryDetail(
        **summary.model_dump(),
        abstract=entry.abstract,
        keywords=_json_list(entry.keywords_json),
        timeline=list(grouped.values()),
        filter_evaluations=filter_evaluations,
        ai_comments=ai_comments,
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
    comment.updated_at = datetime.now(UTC)
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

        winner, loser = entry, other_entry

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
                    ReadingItem.owner_user_id == user.id,
                )
            )
        ).scalars().all()
        for ri in ri_rows:
            ri.bib_entry_id = winner.id

        await db.delete(loser)

        updated_fields = ["merged_with_local"]
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
    entry.dedup_key = compute_dedup_key(
        normalize_doi(new_doi) or new_doi,
        new_title,
        new_authors,
        new_year,
    )

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
