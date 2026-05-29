"""Reference tracing router for bibliography extraction and citation alignment."""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


def _clean_for_excel(text):
    """Remove control characters that Excel cannot handle (except tab, LF, CR)."""
    if not isinstance(text, str):
        return text
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import AsyncSessionLocal, get_db
from db.models import (
    Artifact,
    BibEntry,
    BibReference,
    BibReferenceCitation,
    File,
    Job,
    JobBibEntry,
    User,
)
from db.utils import compute_dedup_key, title_match_score
from services.deepseek_refs import (
    extract_references_deepseek,
    trace_citations_deepseek,
)
from result_storage import build_result_storage_path, get_results_root
from upload_storage import resolve_storage_path


router = APIRouter()
RESULTS_ROOT = get_results_root()

tasks: dict[str, dict] = {}

REFERENCE_HEADINGS = {
    "references",
    "bibliography",
    "works cited",
    "参考文献",
}


class ReferenceTraceStartRequest(BaseModel):
    api_key: Optional[str] = None


class ReferenceTraceEntryOption(BaseModel):
    id: str
    title: str
    year: Optional[int]
    authors: list[str]
    source_file_name: Optional[str]
    has_reference_trace: bool
    latest_task_id: Optional[str]
    latest_task_status: Optional[str]
    latest_task_finished_at: Optional[str]


class ArtifactResponse(BaseModel):
    id: int
    artifact_type: str
    filename: str
    storage_path: str
    created_at: Optional[str]


class LatestTaskResponse(BaseModel):
    id: str
    status: str
    current_stage: Optional[str]
    finished_at: Optional[str]
    artifacts: list[ArtifactResponse]


class ReferenceTraceSummaryResponse(BaseModel):
    source_bib_entry_id: str
    reference_count: int
    matched_count: int
    imported_count: int
    unmatched_count: int
    citation_hit_count: int
    latest_task: Optional[LatestTaskResponse]


class ReferenceListItem(BaseModel):
    id: str
    reference_order: int
    raw_text: str
    title: Optional[str]
    authors: list[str]
    year: Optional[int]
    journal: Optional[str]
    doi: Optional[str]
    match_method: Optional[str]
    match_score: Optional[float]
    citation_count: int
    matched_bib_entry_id: Optional[str]
    matched_bib_title: Optional[str]


class ReferenceCitationItem(BaseModel):
    id: str
    citation_index: int
    page_label: Optional[str]
    paragraph_label: Optional[str]
    quote_text: str
    excerpt: Optional[str]
    match_method: Optional[str]
    confidence: Optional[float]


class ReferenceImportResponse(BaseModel):
    bib_entry_id: str
    title: str
    source: str


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compute_expires_at(user: User) -> datetime | None:
    if user.role == "normal":
        return utcnow_naive() + timedelta(hours=24)
    return None


def dt_to_str(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def json_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def is_reference_heading(line: str) -> bool:
    stripped = normalize_whitespace(line).strip(":：").lower()
    if stripped in REFERENCE_HEADINGS:
        return True
    return bool(re.match(r"^\d+(\.\d+)*\s*(references|bibliography|works cited|参考文献)$", stripped))


def is_reference_boundary(line: str, current: list[str]) -> bool:
    if re.match(r"^(?:\[\d+\]|\d{1,3}[.)、])\s*", line):
        return True
    if not current:
        return False
    current_text = " ".join(current)
    if len(current_text) < 60:
        return False
    if re.match(r"^[A-Z][A-Za-z'`\-]+(?:,\s*[A-Z][A-Za-z'`\-.\s]+){0,5}", line):
        return True
    if re.match(r"^[\u4e00-\u9fff]{1,6}[,，、\s].{0,40}(19|20)\d{2}", line):
        return True
    return False


def clean_reference_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = normalize_whitespace(raw)
        if not stripped:
            continue
        if stripped.startswith("Page ") or re.fullmatch(r"\d+", stripped):
            continue
        lines.append(stripped)
    return lines


def split_references(text: str) -> list[str]:
    lines = clean_reference_lines(text)
    entries: list[str] = []
    current: list[str] = []
    for line in lines:
        if is_reference_boundary(line, current) and current:
            entries.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(" ".join(current).strip())

    if len(entries) <= 1:
        joined = "\n".join(lines)
        chunks = re.split(r"(?m)(?=^(?:\[\d+\]|\d{1,3}[.)、])\s*)", joined)
        fallback = [normalize_whitespace(chunk) for chunk in chunks if normalize_whitespace(chunk)]
        if len(fallback) > len(entries):
            entries = fallback

    return [entry for entry in entries if len(entry) >= 20]


def normalize_doi(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = value.strip()
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).rstrip(".,;)").lower()


def parse_authors(raw_text: str, year_match: re.Match[str] | None) -> list[str]:
    author_text = raw_text if year_match is None else raw_text[: year_match.start()]
    author_text = re.sub(r"^\s*(?:\[\d+\]|\d{1,3}[.)、])\s*", "", author_text).strip(" .;:")
    if not author_text:
        return []
    if re.search(r"[\u4e00-\u9fff]", author_text):
        parts = re.split(r"[、，,;；]+", author_text)
    else:
        author_text = author_text.replace(" & ", ", ").replace(" and ", ", ")
        parts = re.split(r";|,(?=\s*[A-Z])", author_text)
    authors = [normalize_whitespace(part).strip(".,") for part in parts if normalize_whitespace(part).strip(".,")]
    return authors[:8]


def parse_reference_metadata(raw_text: str) -> dict:
    text = normalize_whitespace(raw_text)
    doi = normalize_doi(text)
    year_match = re.search(r"(19|20)\d{2}[a-z]?", text, flags=re.IGNORECASE)
    year = None
    if year_match:
        year_digits = re.search(r"(19|20)\d{2}", year_match.group(0))
        year = int(year_digits.group(0)) if year_digits else None

    authors = parse_authors(text, year_match)
    after_year = text
    if year_match:
        after_year = text[year_match.end() :].lstrip(").].,:; ")
    after_year = re.sub(r"^\s*(?:[A-Z]\.)+\s*", "", after_year)

    title = None
    title_match = re.search(r"[“\"]([^”\"]+)[”\"]", after_year)
    if title_match:
        title = normalize_whitespace(title_match.group(1))
    elif "[J]" in after_year:
        title = normalize_whitespace(after_year.split("[J]", 1)[0].strip(" .;:"))
    else:
        title = normalize_whitespace(re.split(r"\.\s+", after_year, maxsplit=1)[0].strip(" .;:"))
    if title and len(title) < 4:
        title = None

    journal = None
    if title and title in after_year:
        remaining = after_year.split(title, 1)[1].lstrip(" .;:[]")
        journal = normalize_whitespace(re.split(r"\.\s+|\s+\d{4}\b", remaining, maxsplit=1)[0].strip(" .;:"))
    volume_issue_match = re.search(r"(\d+)\s*\(([^)]+)\)", text)
    pages_match = re.search(r"(\d+\s*[-–]\s*\d+)", text)
    volume = volume_issue_match.group(1) if volume_issue_match else None
    issue = volume_issue_match.group(2).strip() if volume_issue_match else None
    pages = pages_match.group(1).replace(" ", "") if pages_match else None

    language = "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"
    dedup_key = compute_dedup_key(doi, title or text[:80], authors, year)
    return {
        "raw_text": text,
        "authors": authors,
        "year": year,
        "title": title,
        "journal": journal or None,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": doi,
        "language": language,
        "dedup_key": dedup_key,
    }


def split_body_and_references(pages: list[str]) -> tuple[list[dict], str]:
    paragraphs: list[dict] = []
    ref_lines: list[str] = []
    in_references = False
    paragraph_id = 0

    for page_number, page_text in enumerate(pages, start=1):
        blocks = re.split(r"\n\s*\n", page_text or "")
        if len(blocks) == 1:
            blocks = page_text.splitlines()
        for block_index, block in enumerate(blocks, start=1):
            lines = [normalize_whitespace(line) for line in block.splitlines() if normalize_whitespace(line)]
            if not lines:
                continue
            if not in_references:
                for line_index, line in enumerate(lines):
                    if is_reference_heading(line):
                        in_references = True
                        ref_lines.extend(lines[line_index + 1 :])
                        break
                if in_references:
                    continue

                paragraph_text = normalize_whitespace(" ".join(lines))
                if len(paragraph_text) < 40:
                    continue
                paragraph_id += 1
                paragraphs.append(
                    {
                        "id": paragraph_id,
                        "page_label": f"第{page_number}页",
                        "paragraph_label": f"P{page_number}-{block_index}",
                        "text": paragraph_text,
                    }
                )
            else:
                ref_lines.extend(lines)

    return paragraphs, "\n".join(ref_lines)


def extract_pdf_pages(file_path: str) -> list[str]:
    reader = PdfReader(file_path)
    pages: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if normalize_whitespace(text):
            pages.append(text)
    if not pages:
        raise ValueError("无法从 PDF 中提取文本。")
    return pages


def build_reference_patterns(reference_order: int, metadata: dict) -> list[tuple[str, str, float]]:
    patterns: list[tuple[str, str, float]] = []
    raw_text = metadata["raw_text"]
    title = metadata.get("title") or ""
    authors = metadata.get("authors") or []
    year = metadata.get("year")

    numeric_match = re.match(r"^\s*(?:\[\s*(\d+)\s*\]|(\d{1,3})[.)、])", raw_text)
    if numeric_match:
        ref_num = numeric_match.group(1) or numeric_match.group(2)
        escaped = re.escape(ref_num)
        patterns.append((rf"[\[［(（]\s*{escaped}\s*[\]］)）]", "numeric", 0.92))
        patterns.append((rf"\b{escaped}\b", "numeric", 0.55))
    else:
        escaped = re.escape(str(reference_order))
        patterns.append((rf"[\[［(（]\s*{escaped}\s*[\]］)）]", "numeric", 0.76))

    first_author = normalize_whitespace(authors[0]) if authors else ""
    if first_author and year:
        surname = re.split(r"[,，\s]", first_author, maxsplit=1)[0]
        surname = re.sub(r"[^\w\u4e00-\u9fff]+", "", surname)
        if surname:
            patterns.append((rf"{re.escape(surname)}.{{0,40}}{year}", "author_year", 0.88))
            patterns.append((rf"\({re.escape(surname)}.{{0,40}}{year}\)", "author_year", 0.9))

    title_keywords = [word for word in re.split(r"[\s:：,，.;；()（）\-]+", title) if len(word) >= 4]
    if title_keywords:
        phrase = re.escape(" ".join(title_keywords[:4]))
        patterns.append((phrase, "title_keyword", 0.62))

    return patterns


def expand_excerpt(paragraph_text: str, start: int, end: int, window: int = 180) -> str:
    excerpt_start = max(0, start - window)
    excerpt_end = min(len(paragraph_text), end + window)
    excerpt = paragraph_text[excerpt_start:excerpt_end].strip()
    if len(excerpt) > 900:
        excerpt = excerpt[:900].rstrip() + "..."
    return excerpt


def trace_citations(reference_order: int, metadata: dict, paragraphs: list[dict]) -> list[dict]:
    citations: list[dict] = []
    seen: set[tuple[int, int, int]] = set()
    patterns = build_reference_patterns(reference_order, metadata)
    for paragraph in paragraphs:
        text = paragraph["text"]
        for pattern, method, confidence in patterns:
            try:
                regex = re.compile(pattern, flags=re.IGNORECASE)
            except re.error:
                continue
            for match in regex.finditer(text):
                key = (paragraph["id"], match.start(), match.end())
                if key in seen:
                    continue
                seen.add(key)
                citations.append(
                    {
                        "page_label": paragraph["page_label"],
                        "paragraph_label": paragraph["paragraph_label"],
                        "quote_text": text[max(0, match.start() - 12) : min(len(text), match.end() + 12)].strip(),
                        "excerpt": expand_excerpt(text, match.start(), match.end()),
                        "char_start": match.start(),
                        "char_end": match.end(),
                        "match_method": method,
                        "confidence": confidence,
                    }
                )
                if len(citations) >= 8:
                    return citations
    return citations


def get_results_dir(user_id: int, job_id: str) -> Path:
    result_dir = RESULTS_ROOT / str(user_id) / job_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def init_task_payload(task_id: str, user_id: int, source_bib_entry_id: str) -> dict:
    return {
        "id": task_id,
        "owner_user_id": user_id,
        "source_bib_entry_id": source_bib_entry_id,
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "result": None,
        "error": None,
        "created_at": utcnow_naive().isoformat(),
    }


async def mark_trace_started(task_id: str, source_bib_entry_id: str, *, stage: str, progress: int) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        source_entry = await db.get(BibEntry, source_bib_entry_id)
        if job is not None:
            job.status = "running"
            job.progress = progress
            job.current_stage = stage
            job.error_msg = None
            job.started_at = utcnow_naive()
        if source_entry is not None:
            source_entry.updated_at = utcnow_naive()
        await db.commit()


def normalize_entry_match(reference: dict, candidate: BibEntry) -> tuple[Optional[str], Optional[float], Optional[str]]:
    ref_doi = normalize_doi(reference.get("doi"))
    candidate_doi = normalize_doi(candidate.doi)
    if ref_doi and candidate_doi and ref_doi == candidate_doi:
        return candidate.id, 1.0, "doi_exact"

    ref_title = reference.get("title") or ""
    if not ref_title:
        return None, None, None

    score = title_match_score(ref_title, candidate.title or "")
    ref_authors = reference.get("authors") or []
    cand_authors = json_list(candidate.authors_json)
    if ref_authors and cand_authors:
        ref_first = normalize_whitespace(ref_authors[0]).split(" ")[0].lower()
        cand_first = normalize_whitespace(cand_authors[0]).split(" ")[0].lower()
        if ref_first and ref_first == cand_first:
            score += 0.08
    if reference.get("year") and candidate.year and reference["year"] == candidate.year:
        score += 0.05
    if score >= 0.82:
        return candidate.id, min(score, 0.99), "title_author_year"
    return None, None, None


async def persist_trace_success(
    task_id: str,
    user_id: int,
    source_bib_entry_id: str,
    references: list[dict],
    artifact_files: list[dict],
) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        source_entry = await db.get(BibEntry, source_bib_entry_id)
        owner = await db.get(User, user_id)
        if job is None or source_entry is None or owner is None:
            return

        candidates = (
            await db.execute(
                select(BibEntry).where(BibEntry.owner_user_id == user_id, BibEntry.id != source_bib_entry_id)
            )
        ).scalars().all()

        old_refs = (
            await db.execute(
                select(BibReference.id).where(BibReference.source_bib_entry_id == source_bib_entry_id)
            )
        ).scalars().all()
        if old_refs:
            await db.execute(
                delete(BibReferenceCitation).where(BibReferenceCitation.bib_reference_id.in_(old_refs))
            )
        await db.execute(delete(BibReference).where(BibReference.source_bib_entry_id == source_bib_entry_id))

        for reference in references:
            matched_id = None
            match_score = None
            match_method = None
            for candidate in candidates:
                matched_id, match_score, match_method = normalize_entry_match(reference, candidate)
                if matched_id:
                    break

            record = BibReference(
                id=str(uuid.uuid4()),
                owner_user_id=user_id,
                source_bib_entry_id=source_bib_entry_id,
                source_job_id=task_id,
                reference_order=reference["reference_order"],
                raw_text=reference["raw_text"],
                authors_json=json.dumps(reference.get("authors", []), ensure_ascii=False),
                year=reference.get("year"),
                title=reference.get("title"),
                journal=reference.get("journal"),
                volume=reference.get("volume"),
                issue=reference.get("issue"),
                pages=reference.get("pages"),
                doi=reference.get("doi"),
                language=reference.get("language"),
                dedup_key=reference.get("dedup_key"),
                matched_bib_entry_id=matched_id,
                match_method=match_method,
                match_score=match_score,
                citation_count=len(reference.get("citations", [])),
                updated_at=utcnow_naive(),
            )
            db.add(record)
            await db.flush()

            for citation_index, citation in enumerate(reference.get("citations", []), start=1):
                db.add(
                    BibReferenceCitation(
                        id=str(uuid.uuid4()),
                        owner_user_id=user_id,
                        source_bib_entry_id=source_bib_entry_id,
                        bib_reference_id=record.id,
                        source_job_id=task_id,
                        citation_index=citation_index,
                        page_label=citation.get("page_label"),
                        paragraph_label=citation.get("paragraph_label"),
                        quote_text=citation["quote_text"],
                        quote_text_zh=None,
                        excerpt=citation.get("excerpt"),
                        char_start=citation.get("char_start"),
                        char_end=citation.get("char_end"),
                        match_method=citation.get("match_method"),
                        confidence=citation.get("confidence"),
                    )
                )

        for sort_order, artifact_info in enumerate(artifact_files):
            absolute_path = Path(artifact_info["absolute_path"])
            db.add(
                Artifact(
                    job_id=task_id,
                    owner_user_id=user_id,
                    artifact_type=artifact_info["artifact_type"],
                    filename=absolute_path.name,
                    storage_path=build_result_storage_path(absolute_path),
                    size_bytes=absolute_path.stat().st_size if absolute_path.exists() else None,
                    sort_order=sort_order,
                    expires_at=compute_expires_at(owner),
                )
            )

        job.status = "success"
        job.progress = 100
        job.current_stage = "完成"
        job.error_msg = None
        job.finished_at = utcnow_naive()
        source_entry.updated_at = utcnow_naive()
        await db.commit()


async def persist_trace_failure(task_id: str, error_message: str, *, canceled: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        if job is None:
            return
        job.status = "canceled" if canceled else "failed"
        job.progress = job.progress or 0
        job.current_stage = "已取消" if canceled else f"错误: {error_message}"
        job.error_msg = None if canceled else error_message
        job.finished_at = utcnow_naive()
        await db.commit()


async def build_task_status_from_db(task_id: str, user_id: int) -> Optional[dict]:
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(select(Job).where(Job.id == task_id, Job.owner_user_id == user_id))
        ).scalar_one_or_none()
        if job is None:
            return None
        artifacts = (
            await db.execute(
                select(Artifact).where(Artifact.job_id == task_id).order_by(Artifact.sort_order, Artifact.id)
            )
        ).scalars().all()
        return {
            "id": job.id,
            "owner_user_id": user_id,
            "status": "completed" if job.status == "success" else job.status,
            "progress": job.progress,
            "stage": job.current_stage or "处理中...",
            "logs": [],
            "result": {
                "artifacts": [
                    {
                        "artifact_type": artifact.artifact_type,
                        "filename": artifact.filename,
                        "storage_path": artifact.storage_path,
                    }
                    for artifact in artifacts
                ]
            }
            if artifacts
            else None,
            "error": job.error_msg,
        }


def write_trace_outputs(
    user_id: int,
    task_id: str,
    source_title: str,
    references: list[dict],
) -> list[dict]:
    result_dir = get_results_dir(user_id, task_id)
    safe_title = re.sub(r'[<>:"/\\|?*]+', "_", source_title).strip()[:80] or task_id
    base_rows = []
    citation_rows = []
    markdown_lines = [f"# 参考文献梳理报告：{source_title}\n\n"]

    for reference in references:
        authors_text = ", ".join(reference.get("authors", []))
        citation_texts = [item.get("excerpt") or item.get("quote_text") for item in reference.get("citations", [])]
        citation_preview = " || ".join(filter(None, citation_texts[:3]))
        base_rows.append(
            {
                "reference_order": reference["reference_order"],
                "raw_text": reference["raw_text"],
                "title": reference.get("title"),
                "authors": authors_text,
                "year": reference.get("year"),
                "journal": reference.get("journal"),
                "doi": reference.get("doi"),
            }
        )
        citation_rows.append(
            {
                **base_rows[-1],
                "citation_count": len(reference.get("citations", [])),
                "matched_bib_entry_id": reference.get("matched_bib_entry_id"),
                "match_method": reference.get("match_method"),
                "match_score": reference.get("match_score"),
                "citation_preview": citation_preview,
            }
        )
        markdown_lines.append(f"## [{reference['reference_order']}] {reference.get('title') or '未识别标题'}\n\n")
        markdown_lines.append(f"- 原文：{reference['raw_text']}\n")
        markdown_lines.append(f"- 命中次数：{len(reference.get('citations', []))}\n")
        if citation_texts:
            for citation in reference["citations"][:5]:
                markdown_lines.append(f"- {citation.get('page_label') or '未知页'}：{citation.get('excerpt') or citation.get('quote_text')}\n")
        markdown_lines.append("\n")

    refs_excel_path = result_dir / f"{safe_title}_references.xlsx"
    refs_with_citations_path = result_dir / f"{safe_title}_references_with_citations.xlsx"
    report_md_path = result_dir / f"{safe_title}_citation_trace.md"
    report_json_path = result_dir / f"{safe_title}_references.json"

    # Clean control characters before writing to Excel (openpyxl rejects \x00-\x08, \x0b, \x0c, \x0e-\x1f)
    df_base = pd.DataFrame(base_rows)
    df_citations = pd.DataFrame(citation_rows)
    for df in (df_base, df_citations):
        for col in df.columns:
            if pd.api.types.is_string_dtype(df[col]):
                df[col] = df[col].apply(_clean_for_excel)
    df_base.to_excel(refs_excel_path, index=False, engine="openpyxl")
    df_citations.to_excel(refs_with_citations_path, index=False, engine="openpyxl")
    report_md_path.write_text("".join(markdown_lines), encoding="utf-8")
    report_json_path.write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding="utf-8")

    return [
        {"artifact_type": "references_excel", "absolute_path": refs_excel_path},
        {"artifact_type": "references_with_citations_excel", "absolute_path": refs_with_citations_path},
        {"artifact_type": "citation_trace_md", "absolute_path": report_md_path},
        {"artifact_type": "references_json", "absolute_path": report_json_path},
    ]


def run_reference_trace_task(task_id: str, user_id: int, source_bib_entry_id: str, file_path: str, source_title: str, api_key: Optional[str] = None) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(mark_trace_started(task_id, source_bib_entry_id, stage="读取文档...", progress=10))
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "读取文档..."
        tasks[task_id]["logs"].append("开始读取文档文本")

        tasks[task_id]["progress"] = 20
        tasks[task_id]["stage"] = "DeepSeek 识别参考文献..."
        tasks[task_id]["logs"].append("调用 DeepSeek 识别参考文献")

        references = extract_references_deepseek(file_path, api_key=api_key)
        if not references:
            raise ValueError("DeepSeek 未识别到任何参考文献。")

        tasks[task_id]["progress"] = 50
        tasks[task_id]["stage"] = "DeepSeek 追踪正文引用..."
        tasks[task_id]["logs"].append(f"识别到 {len(references)} 条参考文献，开始追踪正文引用")

        references = trace_citations_deepseek(file_path, references, api_key=api_key)

        for ref in references:
            ref["dedup_key"] = compute_dedup_key(
                ref.get("doi"), ref.get("title") or ref.get("raw_text", "")[:80],
                ref.get("authors", []), ref.get("year"),
            )
            ref.setdefault("citations", [])

        tasks[task_id]["progress"] = 85
        tasks[task_id]["stage"] = "生成结果产物..."
        tasks[task_id]["logs"].append("正在生成 Excel / Markdown / JSON")

        artifact_files = write_trace_outputs(user_id, task_id, source_title, references)
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "写入数据库..."

        loop.run_until_complete(
            persist_trace_success(
                task_id,
                user_id,
                source_bib_entry_id,
                references,
                artifact_files,
            )
        )

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("参考文献梳理完成")
        tasks[task_id]["result"] = {
            "artifacts": [
                {
                    "artifact_type": item["artifact_type"],
                    "storage_path": build_result_storage_path(Path(item["absolute_path"])),
                }
                for item in artifact_files
            ]
        }
    except Exception as exc:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {exc}"
        tasks[task_id]["logs"].append(f"❌ {exc}")
        tasks[task_id]["error"] = str(exc)
        try:
            loop.run_until_complete(persist_trace_failure(task_id, str(exc)))
        except Exception:
            pass
    finally:
        loop.close()


async def get_owned_entry_with_file(db: AsyncSession, user: User, entry_id: str) -> tuple[BibEntry, File]:
    row = (
        await db.execute(
            select(BibEntry, File)
            .join(File, File.id == BibEntry.source_file_id)
            .where(
                BibEntry.id == entry_id,
                BibEntry.owner_user_id == user.id,
                File.file_type.in_(["pdf", "markdown"]),
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到带 PDF/Markdown 的源文献。")
    return row


async def latest_reference_task(db: AsyncSession, user_id: int, entry_id: str) -> tuple[Optional[Job], list[Artifact]]:
    latest_job = (
        await db.execute(
            select(Job)
            .join(JobBibEntry, JobBibEntry.job_id == Job.id)
            .where(
                Job.owner_user_id == user_id,
                Job.job_type == "reference_trace",
                JobBibEntry.bib_entry_id == entry_id,
                JobBibEntry.role == "reference_source",
            )
            .order_by(Job.created_at.desc())
        )
    ).scalars().first()
    if latest_job is None:
        return None, []
    artifacts = (
        await db.execute(
            select(Artifact).where(Artifact.job_id == latest_job.id).order_by(Artifact.sort_order, Artifact.id)
        )
    ).scalars().all()
    return latest_job, list(artifacts)


@router.get("/entries", response_model=list[ReferenceTraceEntryOption])
async def list_reference_trace_entries(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReferenceTraceEntryOption]:
    rows = (
        await db.execute(
            select(BibEntry, File)
            .join(File, File.id == BibEntry.source_file_id)
            .where(BibEntry.owner_user_id == user.id, File.file_type.in_(["pdf", "markdown"]))
            .order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc())
        )
    ).all()

    items: list[ReferenceTraceEntryOption] = []
    for entry, file_record in rows:
        latest_job, _artifacts = await latest_reference_task(db, user.id, entry.id)
        has_reference_trace = (
            await db.execute(select(BibReference.id).where(BibReference.source_bib_entry_id == entry.id))
        ).first() is not None
        items.append(
            ReferenceTraceEntryOption(
                id=entry.id,
                title=entry.title,
                year=entry.year,
                authors=json_list(entry.authors_json),
                source_file_name=file_record.original_name,
                has_reference_trace=has_reference_trace,
                latest_task_id=latest_job.id if latest_job else None,
                latest_task_status=latest_job.status if latest_job else None,
                latest_task_finished_at=dt_to_str(latest_job.finished_at) if latest_job else None,
            )
        )
    return items


@router.post("/entries/{entry_id}/trace")
async def start_reference_trace(
    entry_id: str,
    _request: ReferenceTraceStartRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    entry, source_file = await get_owned_entry_with_file(db, user, entry_id)
    source_path = resolve_storage_path(source_file.storage_path)
    if not source_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源文件不存在。")

    task_id = str(uuid.uuid4())
    job = Job(
        id=task_id,
        owner_user_id=user.id,
        job_type="reference_trace",
        status="pending",
        input_file_id=source_file.id,
        params_json=json.dumps({"source_bib_entry_id": entry.id}, ensure_ascii=False),
        progress=0,
        current_stage="等待开始...",
        expires_at=compute_expires_at(user),
    )
    db.add(job)
    db.add(
        JobBibEntry(
            job_id=task_id,
            bib_entry_id=entry.id,
            role="reference_source",
            sort_order=0,
        )
    )
    await db.commit()

    tasks[task_id] = init_task_payload(task_id, user.id, entry.id)
    thread = threading.Thread(
        target=run_reference_trace_task,
        args=(task_id, user.id, entry.id, str(source_path), entry.title, _request.api_key),
        daemon=True,
    )
    thread.start()
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}/status")
async def get_reference_task_status(
    task_id: str,
    user: User = Depends(current_user),
) -> dict:
    if task_id in tasks and tasks[task_id].get("owner_user_id") == user.id:
        return tasks[task_id]
    payload = await build_task_status_from_db(task_id, user.id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在。")
    return payload


@router.get("/entries/{entry_id}/summary", response_model=ReferenceTraceSummaryResponse)
async def get_reference_trace_summary(
    entry_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ReferenceTraceSummaryResponse:
    await get_owned_entry_with_file(db, user, entry_id)
    references = (
        await db.execute(
            select(BibReference).where(BibReference.source_bib_entry_id == entry_id).order_by(BibReference.reference_order)
        )
    ).scalars().all()
    latest_job, artifacts = await latest_reference_task(db, user.id, entry_id)
    matched_count = sum(1 for item in references if item.matched_bib_entry_id)
    imported_count = sum(1 for item in references if item.match_method == "imported")
    citation_hit_count = sum(int(item.citation_count or 0) for item in references)
    latest_task = None
    if latest_job is not None:
        latest_task = LatestTaskResponse(
            id=latest_job.id,
            status=latest_job.status,
            current_stage=latest_job.current_stage,
            finished_at=dt_to_str(latest_job.finished_at),
            artifacts=[
                ArtifactResponse(
                    id=item.id,
                    artifact_type=item.artifact_type,
                    filename=item.filename,
                    storage_path=item.storage_path,
                    created_at=dt_to_str(item.created_at),
                )
                for item in artifacts
            ],
        )
    return ReferenceTraceSummaryResponse(
        source_bib_entry_id=entry_id,
        reference_count=len(references),
        matched_count=matched_count,
        imported_count=imported_count,
        unmatched_count=max(0, len(references) - matched_count),
        citation_hit_count=citation_hit_count,
        latest_task=latest_task,
    )


@router.get("/entries/{entry_id}/references", response_model=list[ReferenceListItem])
async def list_references_for_entry(
    entry_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReferenceListItem]:
    await get_owned_entry_with_file(db, user, entry_id)
    references = (
        await db.execute(
            select(BibReference).where(BibReference.source_bib_entry_id == entry_id).order_by(BibReference.reference_order)
        )
    ).scalars().all()
    matched_ids = [item.matched_bib_entry_id for item in references if item.matched_bib_entry_id]
    matched_map: dict[str, str] = {}
    if matched_ids:
        matched_entries = (
            await db.execute(select(BibEntry).where(BibEntry.id.in_(matched_ids), BibEntry.owner_user_id == user.id))
        ).scalars().all()
        matched_map = {item.id: item.title for item in matched_entries}
    return [
        ReferenceListItem(
            id=item.id,
            reference_order=item.reference_order,
            raw_text=item.raw_text,
            title=item.title,
            authors=json_list(item.authors_json),
            year=item.year,
            journal=item.journal,
            doi=item.doi,
            match_method=item.match_method,
            match_score=item.match_score,
            citation_count=item.citation_count,
            matched_bib_entry_id=item.matched_bib_entry_id,
            matched_bib_title=matched_map.get(item.matched_bib_entry_id or ""),
        )
        for item in references
    ]


@router.get("/references/{reference_id}/citations", response_model=list[ReferenceCitationItem])
async def list_reference_citations(
    reference_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ReferenceCitationItem]:
    reference = (
        await db.execute(
            select(BibReference).where(BibReference.id == reference_id, BibReference.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="参考文献不存在。")
    citations = (
        await db.execute(
            select(BibReferenceCitation)
            .where(BibReferenceCitation.bib_reference_id == reference_id)
            .order_by(BibReferenceCitation.citation_index)
        )
    ).scalars().all()
    return [
        ReferenceCitationItem(
            id=item.id,
            citation_index=item.citation_index,
            page_label=item.page_label,
            paragraph_label=item.paragraph_label,
            quote_text=item.quote_text,
            excerpt=item.excerpt,
            match_method=item.match_method,
            confidence=item.confidence,
        )
        for item in citations
    ]


@router.post("/references/{reference_id}/import", response_model=ReferenceImportResponse)
async def import_reference_to_library(
    reference_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ReferenceImportResponse:
    reference = (
        await db.execute(
            select(BibReference).where(BibReference.id == reference_id, BibReference.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="参考文献不存在。")

    if reference.matched_bib_entry_id:
        matched = await db.get(BibEntry, reference.matched_bib_entry_id)
        if matched is not None:
            return ReferenceImportResponse(bib_entry_id=matched.id, title=matched.title, source="existing")

    authors = json_list(reference.authors_json)
    title = (reference.title or "").strip() or reference.raw_text[:80]
    dedup_key = compute_dedup_key(reference.doi, title, authors, reference.year)
    existing = (
        await db.execute(
            select(BibEntry).where(BibEntry.owner_user_id == user.id, BibEntry.dedup_key == dedup_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        reference.matched_bib_entry_id = existing.id
        reference.match_method = "imported"
        reference.match_score = 1.0
        reference.updated_at = utcnow_naive()
        await db.commit()
        return ReferenceImportResponse(bib_entry_id=existing.id, title=existing.title, source="existing")

    completeness = "minimal"
    if title and authors:
        completeness = "partial"
    if title and authors and reference.year and reference.doi and reference.journal:
        completeness = "full"

    bib_entry = BibEntry(
        id=str(uuid.uuid4()),
        owner_user_id=user.id,
        title=title,
        authors_json=json.dumps(authors, ensure_ascii=False),
        year=reference.year,
        doi=reference.doi,
        journal=reference.journal,
        abstract=None,
        keywords_json="[]",
        venue_type=None,
        citation_count=None,
        source_db="manual",
        source_filter_job_id=None,
        source_file_id=None,
        user_tags_json="[]",
        user_note=f"由参考文献梳理导入：{reference.raw_text[:200]}",
        is_pinned=0,
        reading_status="none",
        metadata_completeness=completeness,
        dedup_key=dedup_key,
        expires_at=compute_expires_at(user),
    )
    db.add(bib_entry)
    await db.flush()

    reference.matched_bib_entry_id = bib_entry.id
    reference.match_method = "imported"
    reference.match_score = 1.0
    reference.updated_at = utcnow_naive()
    await db.commit()
    return ReferenceImportResponse(bib_entry_id=bib_entry.id, title=bib_entry.title, source="created")


class ReferenceUpdateRequest(BaseModel):
    title: Optional[str] = None
    authors: Optional[list[str]] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    raw_text: Optional[str] = None


@router.put("/references/{reference_id}", response_model=ReferenceListItem)
async def update_reference(
    reference_id: str,
    body: ReferenceUpdateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> ReferenceListItem:
    reference = (
        await db.execute(
            select(BibReference).where(BibReference.id == reference_id, BibReference.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if reference is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="参考文献不存在。")

    updates = body.model_dump(exclude_none=True)
    if "authors" in updates:
        updates["authors_json"] = json.dumps(updates.pop("authors"), ensure_ascii=False)
    for field, value in updates.items():
        if hasattr(reference, field):
            setattr(reference, field, value)
    reference.updated_at = utcnow_naive()
    await db.commit()
    await db.refresh(reference)

    matched_title = None
    if reference.matched_bib_entry_id:
        matched = await db.get(BibEntry, reference.matched_bib_entry_id)
        matched_title = matched.title if matched else None

    return ReferenceListItem(
        id=reference.id,
        reference_order=reference.reference_order,
        raw_text=reference.raw_text,
        title=reference.title,
        authors=json_list(reference.authors_json),
        year=reference.year,
        journal=reference.journal,
        doi=reference.doi,
        match_method=reference.match_method,
        match_score=reference.match_score,
        citation_count=reference.citation_count,
        matched_bib_entry_id=reference.matched_bib_entry_id,
        matched_bib_title=matched_title,
    )
