from __future__ import annotations

import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BibEntry, File
from db.utils import compute_dedup_key, normalize_doi, normalize_title_for_match, title_match_score
from upload_storage import resolve_storage_path


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class MarkdownLibraryMetadata:
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    journal: str | None
    abstract: str | None
    keywords: list[str]
    volume: str | None
    issue: str | None
    pages: str | None
    language: str | None
    has_structured_metadata: bool


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _frontmatter_text(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, flags=re.S)
    return match.group(1) if match else None


def _parse_authors(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[;；,，、]+", value) if part.strip()]
    return []


def _parse_keywords(raw: dict[str, Any]) -> list[str]:
    value = raw.get("keywords")
    if value is None:
        value = raw.get("tags")
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[;；,，、\s]+", value) if part.strip()]
    return []


def _parse_year(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d{4}", str(value))
    if not match:
        return None
    year = int(match.group(0))
    if 1800 <= year <= 2100:
        return year
    return None


def _fallback_title(original_name: str) -> str:
    normalized_name = original_name.replace("\\", "/")
    stem = Path(normalized_name).stem
    return re.sub(r"(?i)(?:_ocr|_paddleocr)$", "", stem).strip()


def _pages(raw: dict[str, Any]) -> str | None:
    start = _clean_text(raw.get("start_page"))
    end = _clean_text(raw.get("end_page"))
    if start and end:
        return f"{start}-{end}"
    return start or end or _clean_text(raw.get("pages"))


def _normalize_language(raw: Any, title: str) -> str | None:
    text = str(raw or "").strip().lower()
    if text in {"en", "zh", "other"}:
        return text
    if text in {"english", "英文"}:
        return "en"
    if text in {"chinese", "中文", "汉语"}:
        return "zh"
    if re.search(r"[\u4e00-\u9fff]", title or ""):
        return "zh"
    return None


def _metadata_completeness(metadata: MarkdownLibraryMetadata) -> str:
    if metadata.title and metadata.authors and metadata.year and metadata.doi and metadata.journal and metadata.abstract:
        return "full"
    if metadata.title and metadata.authors:
        return "partial"
    return "minimal"


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []


def parse_markdown_library_metadata(path: Path, original_name: str) -> MarkdownLibraryMetadata:
    text = path.read_text(encoding="utf-8", errors="ignore")[:20000]
    raw: dict[str, Any] = {}
    fm = _frontmatter_text(text)
    if fm:
        parsed = yaml.safe_load(fm) or {}
        if isinstance(parsed, dict):
            raw = parsed

    title = _clean_text(raw.get("title")) or _fallback_title(original_name)
    doi = normalize_doi(_clean_text(raw.get("doi")))
    authors = _parse_authors(raw.get("authors"))
    year = _parse_year(raw.get("year"))
    journal = _clean_text(raw.get("journal"))
    abstract = _clean_text(raw.get("abstract"))
    structured_values = [raw.get("title"), doi, authors, year, journal, abstract, raw.get("citation"), raw.get("source_file")]
    return MarkdownLibraryMetadata(
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        journal=journal,
        abstract=abstract,
        keywords=_parse_keywords(raw),
        volume=_clean_text(raw.get("volume")),
        issue=_clean_text(raw.get("issue")),
        pages=_pages(raw),
        language=_normalize_language(raw.get("language"), title),
        has_structured_metadata=bool(raw) and any(bool(value) for value in structured_values),
    )


def _dedup_key(metadata: MarkdownLibraryMetadata) -> str:
    return compute_dedup_key(metadata.doi, metadata.title, metadata.authors, metadata.year)


def _compatible_year(left: int | None, right: int | None) -> bool:
    return left is None or right is None or left == right


def _author_token(author: str) -> str:
    normalized = unicodedata.normalize("NFKC", author or "").strip().lower()
    return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)


def _compatible_first_author(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return True
    return _author_token(left[0]) == _author_token(right[0])


async def _find_existing_entry(db: AsyncSession, owner_user_id: int, metadata: MarkdownLibraryMetadata) -> BibEntry | None:
    if metadata.doi:
        doi_matches = (
            await db.execute(
                select(BibEntry).where(BibEntry.owner_user_id == owner_user_id, BibEntry.doi.isnot(None))
            )
        ).scalars().all()
        for entry in doi_matches:
            if normalize_doi(entry.doi) == metadata.doi:
                return entry

    key = _dedup_key(metadata)
    entry = (
        await db.execute(
            select(BibEntry).where(BibEntry.owner_user_id == owner_user_id, BibEntry.dedup_key == key)
        )
    ).scalar_one_or_none()
    if entry is not None:
        return entry

    title_norm = normalize_title_for_match(metadata.title)
    if not title_norm:
        return None
    candidates = (
        await db.execute(select(BibEntry).where(BibEntry.owner_user_id == owner_user_id))
    ).scalars().all()
    best_entry: BibEntry | None = None
    best_score = 0.0
    for candidate in candidates:
        if not _compatible_year(metadata.year, candidate.year):
            continue
        if not _compatible_first_author(metadata.authors, _json_list(candidate.authors_json)):
            continue
        score = title_match_score(metadata.title, candidate.title or "")
        if score > best_score:
            best_score = score
            best_entry = candidate
    if best_entry is not None and best_score >= 0.92:
        return best_entry
    return None


def _fill_empty_fields(entry: BibEntry, metadata: MarkdownLibraryMetadata) -> None:
    if (not entry.authors_json or entry.authors_json == "[]") and metadata.authors:
        entry.authors_json = json.dumps(metadata.authors, ensure_ascii=False)
    if entry.year is None and metadata.year is not None:
        entry.year = metadata.year
    if not entry.doi and metadata.doi:
        entry.doi = metadata.doi
    if not entry.journal and metadata.journal:
        entry.journal = metadata.journal
    if not entry.abstract and metadata.abstract:
        entry.abstract = metadata.abstract
    if (not entry.keywords_json or entry.keywords_json == "[]") and metadata.keywords:
        entry.keywords_json = json.dumps(metadata.keywords, ensure_ascii=False)
    if not entry.volume and metadata.volume:
        entry.volume = metadata.volume
    if not entry.issue and metadata.issue:
        entry.issue = metadata.issue
    if not entry.pages and metadata.pages:
        entry.pages = metadata.pages
    if not entry.language and metadata.language:
        entry.language = metadata.language

    authors = _json_list(entry.authors_json)
    entry.metadata_completeness = _metadata_completeness(
        MarkdownLibraryMetadata(
            title=entry.title,
            authors=authors,
            year=entry.year,
            doi=entry.doi,
            journal=entry.journal,
            abstract=entry.abstract,
            keywords=_json_list(entry.keywords_json),
            volume=entry.volume,
            issue=entry.issue,
            pages=entry.pages,
            language=entry.language,
            has_structured_metadata=True,
        )
    )


async def import_markdown_file_to_library(db: AsyncSession, *, owner_user_id: int, record: File) -> BibEntry | None:
    if record.file_type != "markdown":
        return None

    path = resolve_storage_path(record.storage_path)
    if not path.exists():
        return None

    metadata = parse_markdown_library_metadata(path, record.original_name)
    if not metadata.has_structured_metadata or not metadata.title:
        return None

    entry = await _find_existing_entry(db, owner_user_id, metadata)
    now = utcnow_naive()
    if entry is not None:
        if not entry.markdown_source_file_id:
            entry.markdown_source_file_id = record.id
        if not entry.source_file_id:
            entry.source_file_id = record.id
        if entry.reading_status == "none":
            entry.reading_status = "has_pdf"
        _fill_empty_fields(entry, metadata)
        entry.updated_at = now
        return entry

    entry = BibEntry(
        id=str(uuid.uuid4()),
        owner_user_id=owner_user_id,
        title=metadata.title,
        authors_json=json.dumps(metadata.authors, ensure_ascii=False),
        year=metadata.year,
        doi=metadata.doi,
        journal=metadata.journal,
        abstract=metadata.abstract,
        abstract_cn=None,
        keywords_json=json.dumps(metadata.keywords, ensure_ascii=False),
        venue_type=None,
        citation_count=None,
        volume=metadata.volume,
        issue=metadata.issue,
        pages=metadata.pages,
        language=metadata.language,
        source_db="md_extracted",
        source_filter_job_id=None,
        source_file_id=record.id,
        markdown_source_file_id=record.id,
        user_tags_json="[]",
        user_note=None,
        is_pinned=0,
        reading_status="has_pdf",
        metadata_completeness=_metadata_completeness(metadata),
        dedup_key=_dedup_key(metadata),
        expires_at=record.expires_at,
    )
    db.add(entry)
    await db.flush()
    return entry
