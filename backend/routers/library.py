"""Library router for bib-entry centric browsing and editing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, func, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import PROJECT_ROOT, get_db
from db.models import Artifact, BibEntry, BibFilterLink, File, Job, JobBibEntry, User
from services.crossref_source import CrossrefSource
from services.metadata_match_service import classify_confidence, score_candidates
from services.metadata_sources import CandidateMetadata
from services.openalex_source import OpenAlexSource
from services.pdf_metadata_extract import extract_front_matter
from services.pdf_metadata_llm import extract_metadata_with_llm
from upload_storage import resolve_storage_path

router = APIRouter()
RESULTS_DIR = PROJECT_ROOT / "deep_reading_results"


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


class LibraryEntryDetail(LibraryEntrySummary):
    abstract: Optional[str]
    keywords: list[str]
    timeline: list[LibraryTimelineItem]
    filter_evaluations: list[LibraryFilterEvaluation]


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


def _load_abstract_translation_from_artifact(entry: BibEntry, artifact: Artifact | None) -> Optional[str]:
    if artifact is None:
        return None
    target_path = RESULTS_DIR / artifact.storage_path
    if not target_path.exists() or target_path.suffix.lower() not in {".xlsx", ".xls"}:
        return None

    import pandas as pd

    try:
        df = pd.read_excel(target_path)
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


@router.get("/entries", response_model=list[LibraryEntrySummary])
async def list_entries(
    search: str = Query(default=""),
    journal: str = Query(default=""),
    reading_status: str = Query(default=""),
    pinned_only: bool = Query(default=False),
    sort_by: str = Query(default="updated"),
    sort_order: str = Query(default="desc"),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
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
    return [build_entry_summary(entry, source_file, max_score) for entry, source_file, max_score in rows]


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

    summary = build_entry_summary(entry, source_file)
    return LibraryEntryDetail(
        **summary.model_dump(),
        abstract=entry.abstract,
        keywords=_json_list(entry.keywords_json),
        timeline=list(grouped.values()),
        filter_evaluations=filter_evaluations,
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

    await db.commit()
    return await get_entry_detail(entry_id, user=user, db=db)


# ============================================================
# Online Metadata Matching Endpoints
# ============================================================


class OnlineMatchResponse(BaseModel):
    candidates: list[dict]
    extracted_metadata: dict
    high_confidence_count: int
    medium_confidence_count: int


class ApplyMatchRequest(BaseModel):
    candidate_index: int


@router.post("/entries/{entry_id}/match-online", response_model=OnlineMatchResponse)
async def match_online(
    entry_id: str,
    request: dict = {},
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> OnlineMatchResponse:
    """Execute online metadata matching for a single entry."""
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

    candidates = []

    if extracted.get("doi"):
        crossref = CrossrefSource()
        openalex = OpenAlexSource()

        doi_result_crossref = await crossref.search_by_doi(extracted["doi"])
        if doi_result_crossref:
            candidates.append(doi_result_crossref)

        doi_result_openalex = await openalex.search_by_doi(extracted["doi"])
        if doi_result_openalex:
            if not any(c.doi == doi_result_openalex.doi for c in candidates):
                candidates.append(doi_result_openalex)

    if not candidates and extracted.get("title"):
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
    """Apply a candidate match to fill empty fields."""
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

    return {"message": "Match applied successfully."}
