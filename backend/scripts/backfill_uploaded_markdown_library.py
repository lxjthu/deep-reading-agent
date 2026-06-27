from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db import AsyncSessionLocal, PROJECT_ROOT as DB_PROJECT_ROOT  # noqa: E402
from db.models import BibEntry, File  # noqa: E402
from db.utils import compute_dedup_key, normalize_doi, normalize_title_for_match, title_match_score  # noqa: E402
from routers.filter import compute_metadata_completeness  # noqa: E402
from upload_storage import resolve_storage_path  # noqa: E402


@dataclass(frozen=True)
class MarkdownMetadata:
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
    source_file: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class FileCandidate:
    id: str
    original_name: str
    storage_path: str
    size_bytes: int
    expires_at: datetime | None
    created_at: datetime | None
    metadata: MarkdownMetadata


@dataclass(frozen=True)
class ExistingEntry:
    id: str
    title: str
    authors: list[str]
    year: int | None
    doi: str | None
    journal: str | None
    abstract: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    source_file_id: str | None
    markdown_source_file_id: str | None
    reading_status: str
    dedup_key: str


@dataclass
class Decision:
    file_id: str
    original_name: str
    title: str
    doi: str | None
    decision: str
    matched_entry_id: str | None = None
    match_method: str | None = None
    score: float | None = None
    reason: str | None = None
    dedup_key: str | None = None


@dataclass
class BackfillPlan:
    decisions: list[Decision]

    def summary(self) -> dict[str, int]:
        return {
            "candidate_files": len(self.decisions),
            "parsed": sum(1 for d in self.decisions if d.decision != "missing_title"),
            "would_create_entries": sum(1 for d in self.decisions if d.decision == "create_entry"),
            "would_link_existing_entries": sum(1 for d in self.decisions if d.decision == "link_existing"),
            "skipped_duplicates": sum(1 for d in self.decisions if d.decision == "duplicate_markdown_candidate"),
            "skipped_ambiguous": sum(1 for d in self.decisions if d.decision == "ambiguous_existing_match"),
            "skipped_missing_title": sum(1 for d in self.decisions if d.decision == "missing_title"),
            "skipped_already_bound": sum(1 for d in self.decisions if d.decision == "already_has_markdown"),
        }


def _frontmatter_text(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, flags=re.S)
    return match.group(1) if match else None


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _strip_ocr_suffix(stem: str) -> str:
    return re.sub(r"(?i)(?:_ocr|_paddleocr)$", "", stem).strip()


def _fallback_title(original_name: str) -> str:
    normalized_name = original_name.replace("\\", "/")
    stem = Path(normalized_name).stem
    return _strip_ocr_suffix(stem)


def _pages(raw: dict[str, Any]) -> str | None:
    start = _clean_text(raw.get("start_page"))
    end = _clean_text(raw.get("end_page"))
    if start and end:
        return f"{start}-{end}"
    return start or end or _clean_text(raw.get("pages"))


def parse_markdown_metadata(path: Path, original_name: str) -> MarkdownMetadata:
    text = path.read_text(encoding="utf-8", errors="ignore")
    raw: dict[str, Any] = {}
    fm = _frontmatter_text(text[:20000])
    if fm:
        parsed = yaml.safe_load(fm) or {}
        if isinstance(parsed, dict):
            raw = parsed

    title = _clean_text(raw.get("title")) or _fallback_title(original_name)
    return MarkdownMetadata(
        title=title,
        authors=_parse_authors(raw.get("authors")),
        year=_parse_year(raw.get("year")),
        doi=normalize_doi(_clean_text(raw.get("doi"))),
        journal=_clean_text(raw.get("journal")),
        abstract=_clean_text(raw.get("abstract")),
        keywords=_parse_keywords(raw),
        volume=_clean_text(raw.get("volume")),
        issue=_clean_text(raw.get("issue")),
        pages=_pages(raw),
        source_file=_clean_text(raw.get("source_file")),
        raw=raw,
    )


def _metadata_completeness_score(candidate: FileCandidate) -> int:
    meta = candidate.metadata
    return sum(
        1
        for value in (
            meta.title,
            meta.authors,
            meta.year,
            meta.doi,
            meta.journal,
            meta.abstract,
            meta.pages,
        )
        if value
    )


def _dedup_key(metadata: MarkdownMetadata) -> str:
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


def _match_entries(candidate: FileCandidate, entries: list[ExistingEntry]) -> tuple[list[ExistingEntry], str | None, float | None]:
    meta = candidate.metadata
    if meta.doi:
        matches = [entry for entry in entries if normalize_doi(entry.doi) == meta.doi]
        if matches:
            return matches, "doi", 1.0

    dedup_key = _dedup_key(meta)
    matches = [entry for entry in entries if entry.dedup_key == dedup_key]
    if matches:
        return matches, "dedup_key", 1.0

    title_norm = normalize_title_for_match(meta.title)
    matches = [
        entry
        for entry in entries
        if title_norm
        and normalize_title_for_match(entry.title) == title_norm
        and _compatible_year(meta.year, entry.year)
    ]
    if matches:
        return matches, "title_exact", 1.0

    scored: list[tuple[float, ExistingEntry]] = []
    for entry in entries:
        if not _compatible_year(meta.year, entry.year):
            continue
        if not _compatible_first_author(meta.authors, entry.authors):
            continue
        score = title_match_score(meta.title, entry.title)
        if score >= 0.93:
            scored.append((score, entry))
    if not scored:
        return [], None, None
    best_score = max(score for score, _ in scored)
    best = [entry for score, entry in scored if score == best_score]
    return best, "title_high", best_score


def _preferred_duplicate(candidates: list[FileCandidate]) -> FileCandidate:
    return sorted(
        candidates,
        key=lambda item: (_metadata_completeness_score(item), item.size_bytes, item.created_at or datetime.min),
        reverse=True,
    )[0]


def plan_bindings(candidates: list[FileCandidate], existing_entries: list[ExistingEntry]) -> BackfillPlan:
    by_dedup: dict[str, list[FileCandidate]] = {}
    for candidate in candidates:
        if candidate.metadata.title:
            by_dedup.setdefault(_dedup_key(candidate.metadata), []).append(candidate)

    duplicate_losers: set[str] = set()
    for group in by_dedup.values():
        if len(group) <= 1:
            continue
        winner = _preferred_duplicate(group)
        duplicate_losers.update(candidate.id for candidate in group if candidate.id != winner.id)

    decisions: list[Decision] = []
    for candidate in sorted(candidates, key=lambda item: item.original_name):
        meta = candidate.metadata
        key = _dedup_key(meta) if meta.title else None
        if not meta.title:
            decisions.append(
                Decision(
                    file_id=candidate.id,
                    original_name=candidate.original_name,
                    title="",
                    doi=meta.doi,
                    decision="missing_title",
                    reason="frontmatter and filename did not provide a title",
                    dedup_key=key,
                )
            )
            continue
        if candidate.id in duplicate_losers:
            decisions.append(
                Decision(
                    file_id=candidate.id,
                    original_name=candidate.original_name,
                    title=meta.title,
                    doi=meta.doi,
                    decision="duplicate_markdown_candidate",
                    reason="another Markdown file has the same dedup key and more complete metadata",
                    dedup_key=key,
                )
            )
            continue

        matches, method, score = _match_entries(candidate, existing_entries)
        if len(matches) > 1:
            decisions.append(
                Decision(
                    file_id=candidate.id,
                    original_name=candidate.original_name,
                    title=meta.title,
                    doi=meta.doi,
                    decision="ambiguous_existing_match",
                    match_method=method,
                    score=score,
                    reason="multiple existing entries matched this Markdown file",
                    dedup_key=key,
                )
            )
            continue
        if len(matches) == 1:
            matched = matches[0]
            if matched.markdown_source_file_id:
                decisions.append(
                    Decision(
                        file_id=candidate.id,
                        original_name=candidate.original_name,
                        title=meta.title,
                        doi=meta.doi,
                        decision="already_has_markdown",
                        matched_entry_id=matched.id,
                        match_method=method,
                        score=score,
                        reason="existing entry already has markdown_source_file_id",
                        dedup_key=key,
                    )
                )
            else:
                decisions.append(
                    Decision(
                        file_id=candidate.id,
                        original_name=candidate.original_name,
                        title=meta.title,
                        doi=meta.doi,
                        decision="link_existing",
                        matched_entry_id=matched.id,
                        match_method=method,
                        score=score,
                        dedup_key=key,
                    )
                )
            continue

        decisions.append(
            Decision(
                file_id=candidate.id,
                original_name=candidate.original_name,
                title=meta.title,
                doi=meta.doi,
                decision="create_entry",
                dedup_key=key,
            )
        )

    return BackfillPlan(decisions=decisions)


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


def _to_existing_entry(entry: BibEntry) -> ExistingEntry:
    return ExistingEntry(
        id=entry.id,
        title=entry.title,
        authors=_json_list(entry.authors_json),
        year=entry.year,
        doi=entry.doi,
        journal=entry.journal,
        abstract=entry.abstract,
        volume=entry.volume,
        issue=entry.issue,
        pages=entry.pages,
        source_file_id=entry.source_file_id,
        markdown_source_file_id=entry.markdown_source_file_id,
        reading_status=entry.reading_status,
        dedup_key=entry.dedup_key,
    )


def _resolve_storage_path(storage_path: str) -> Path:
    path = resolve_storage_path(storage_path)
    if path.exists():
        return path
    fallback = DB_PROJECT_ROOT / storage_path
    return fallback


async def load_candidates(
    owner_user_id: int,
    storage_prefix: str,
    created_after: datetime | None,
    created_before: datetime | None,
) -> list[FileCandidate]:
    async with AsyncSessionLocal() as db:
        conditions = [
            File.owner_user_id == owner_user_id,
            File.file_type == "markdown",
            File.storage_path.like(f"{storage_prefix}%"),
        ]
        if created_after is not None:
            conditions.append(File.created_at >= created_after)
        if created_before is not None:
            conditions.append(File.created_at <= created_before)
        rows = (
            await db.execute(select(File).where(and_(*conditions)).order_by(File.created_at.asc(), File.id.asc()))
        ).scalars().all()

    candidates: list[FileCandidate] = []
    for record in rows:
        path = _resolve_storage_path(record.storage_path)
        if not path.exists():
            continue
        metadata = parse_markdown_metadata(path, record.original_name)
        if not (
            record.original_name.lower().endswith("_ocr.md")
            or metadata.raw.get("extractor")
            or metadata.source_file
        ):
            continue
        candidates.append(
            FileCandidate(
                id=record.id,
                original_name=record.original_name,
                storage_path=record.storage_path,
                size_bytes=record.size_bytes,
                expires_at=record.expires_at,
                created_at=record.created_at,
                metadata=metadata,
            )
        )
    return candidates


async def load_existing_entries(owner_user_id: int) -> list[ExistingEntry]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(select(BibEntry).where(BibEntry.owner_user_id == owner_user_id))
        ).scalars().all()
    return [_to_existing_entry(entry) for entry in rows]


def build_report(plan: BackfillPlan, *, applied: bool, error: str | None = None) -> dict[str, Any]:
    summary = plan.summary()
    summary["applied"] = int(applied)
    report: dict[str, Any] = {
        "summary": summary,
        "decisions": [asdict(decision) for decision in plan.decisions],
    }
    if error:
        report["error"] = error
    return report


def write_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _fill_empty_entry_fields(entry: BibEntry, metadata: MarkdownMetadata) -> None:
    if not entry.authors_json or entry.authors_json == "[]":
        entry.authors_json = json.dumps(metadata.authors, ensure_ascii=False)
    if entry.year is None and metadata.year is not None:
        entry.year = metadata.year
    if not entry.doi and metadata.doi:
        entry.doi = metadata.doi
    if not entry.journal and metadata.journal:
        entry.journal = metadata.journal
    if not entry.abstract and metadata.abstract:
        entry.abstract = metadata.abstract
    if not entry.keywords_json or entry.keywords_json == "[]":
        entry.keywords_json = json.dumps(metadata.keywords, ensure_ascii=False)
    if not entry.volume and metadata.volume:
        entry.volume = metadata.volume
    if not entry.issue and metadata.issue:
        entry.issue = metadata.issue
    if not entry.pages and metadata.pages:
        entry.pages = metadata.pages
    entry.metadata_completeness = compute_metadata_completeness(
        entry.title,
        _json_list(entry.authors_json),
        entry.year,
        entry.doi,
        entry.journal,
        entry.abstract,
    )


async def apply_plan(owner_user_id: int, candidates: list[FileCandidate], plan: BackfillPlan) -> None:
    by_file_id = {candidate.id: candidate for candidate in candidates}
    async with AsyncSessionLocal() as db:
        async with db.begin():
            for decision in plan.decisions:
                if decision.decision not in {"create_entry", "link_existing"}:
                    continue
                candidate = by_file_id[decision.file_id]
                metadata = candidate.metadata
                if decision.decision == "link_existing":
                    entry = await db.get(BibEntry, decision.matched_entry_id)
                    if entry is None or entry.owner_user_id != owner_user_id:
                        continue
                    if not entry.markdown_source_file_id:
                        entry.markdown_source_file_id = candidate.id
                    if not entry.source_file_id:
                        entry.source_file_id = candidate.id
                    if entry.reading_status == "none":
                        entry.reading_status = "has_pdf"
                    _fill_empty_entry_fields(entry, metadata)
                    entry.updated_at = datetime.now()
                    continue

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
                    language="zh",
                    source_db="md_extracted",
                    source_filter_job_id=None,
                    source_file_id=candidate.id,
                    markdown_source_file_id=candidate.id,
                    user_tags_json="[]",
                    user_note=None,
                    is_pinned=0,
                    reading_status="has_pdf",
                    metadata_completeness=compute_metadata_completeness(
                        metadata.title,
                        metadata.authors,
                        metadata.year,
                        metadata.doi,
                        metadata.journal,
                        metadata.abstract,
                    ),
                    dedup_key=_dedup_key(metadata),
                    expires_at=candidate.expires_at,
                )
                db.add(entry)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill uploaded OCR Markdown files into library entries.")
    parser.add_argument("--owner-user-id", type=int, required=True)
    parser.add_argument("--storage-prefix", required=True)
    parser.add_argument("--created-after")
    parser.add_argument("--created-before")
    parser.add_argument("--report-path", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_after = parse_datetime(args.created_after)
    created_before = parse_datetime(args.created_before)
    report_path = Path(args.report_path)

    candidates = await load_candidates(args.owner_user_id, args.storage_prefix, created_after, created_before)
    existing_entries = await load_existing_entries(args.owner_user_id)
    plan = plan_bindings(candidates, existing_entries)

    if not args.apply:
        report = build_report(plan, applied=False)
        write_report(report, report_path)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        return 0

    try:
        await apply_plan(args.owner_user_id, candidates, plan)
    except IntegrityError as exc:
        report = build_report(plan, applied=False, error=f"integrity_error: {exc}")
        write_report(report, report_path)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        return 2

    report = build_report(plan, applied=True)
    write_report(report, report_path)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
