"""Filter Router - authenticated literature filtering with DB persistence."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from auth.dependencies import current_user
from db import AsyncSessionLocal, get_db
from db.models import Artifact, BibEntry, BibFilterLink, File, Job, User
from db.utils import compute_dedup_key, title_match_score, normalize_doi
from prompt_service import get_effective_prompt_text
from result_storage import build_result_storage_path, get_results_root
from upload_storage import lookup_path_by_file_id
from backend.utils.api_key import validate_deepseek_key
from parsers import get_parser

# Add parent directory to path to import existing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()


def _clean_for_excel(text):
    """Remove control characters that Excel cannot handle (except tab, LF, CR)."""
    if not isinstance(text, str):
        return text
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)

# In-memory task store (runtime cache; DB is the source of truth)
tasks = {}
RESULTS_ROOT = get_results_root()


class FilterRequest(BaseModel):
    file_id: str
    mode: str  # explorer, reviewer, empiricist
    topic: str
    min_year: int = 0
    keywords: Optional[str] = None
    api_key: Optional[str] = None


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compute_expires_at(user: User) -> datetime | None:
    if user.role == "normal":
        return utcnow_naive() + timedelta(hours=24)
    return None


def get_filter_results_dir(user_id: int, job_id: str) -> Path:
    directory = RESULTS_ROOT / str(user_id) / job_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def get_file_path(file_id: str) -> Optional[str]:
    """Resolve uploaded file by file_id across the new user-isolated layout."""
    path = lookup_path_by_file_id(file_id)
    return str(path) if path is not None else None


def parse_authors(raw_authors: Any) -> list[str]:
    if raw_authors is None:
        return []
    if isinstance(raw_authors, list):
        items = raw_authors
    else:
        text = str(raw_authors).strip()
        if not text:
            return []
        normalized = text.replace("；", ";").replace(",", ";").replace(" and ", ";")
        items = [part.strip() for part in normalized.split(";")]
    return [item for item in items if item]


def parse_keywords(raw_keywords: Any) -> list[str]:
    if raw_keywords is None:
        return []
    if isinstance(raw_keywords, list):
        items = raw_keywords
    else:
        text = str(raw_keywords).strip()
        if not text:
            return []
        normalized = (
            text.replace("；", ";")
            .replace("，", ";")
            .replace(",", ";")
            .replace("|", ";")
        )
        items = [part.strip() for part in normalized.split(";")]
    return [item for item in items if item]


def parse_year(raw_year: Any) -> int | None:
    if raw_year is None:
        return None
    text = str(raw_year).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 4:
        return int(digits[:4])
    return None


def parse_int(raw_value: Any) -> int | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return int(digits)
    return None


def infer_source_db(df, file_record: File) -> str:
    source_values = set()
    if "SourceType" in df.columns:
        source_values = {
            str(value).strip().lower() for value in df["SourceType"].dropna().tolist() if str(value).strip()
        }
    if any("wos" in value or "web of science" in value for value in source_values):
        return "wos"
    if any("cnki" in value for value in source_values):
        return "cnki"
    if file_record.original_name.lower().endswith(".txt"):
        if "wos" in file_record.original_name.lower():
            return "wos"
        if "cnki" in file_record.original_name.lower():
            return "cnki"
    return "other"


def compute_metadata_completeness(title: str, authors: list[str], year: int | None, doi: str | None, journal: str | None, abstract: str | None) -> str:
    has_title = bool(title.strip())
    has_authors = bool(authors)
    has_year = year is not None
    has_doi = bool((doi or "").strip())
    has_journal = bool((journal or "").strip())
    has_abstract = bool((abstract or "").strip())
    if has_title and has_authors and has_year and has_doi and has_journal and has_abstract:
        return "full"
    if has_title and has_authors:
        return "partial"
    return "minimal"


def clean_nullable_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def sync_job_status(task_id: str, **updates: Any) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        if job is None:
            return
        for key, value in updates.items():
            setattr(job, key, value)
        await db.commit()


async def reverse_match_to_existing_files(
    db,
    new_entry: BibEntry,
    user_id: int,
) -> None:
    existing_entries = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == user_id,
                BibEntry.source_file_id.isnot(None),
                BibEntry.id != new_entry.id,
            )
        )
    ).scalars().all()

    if not existing_entries:
        return

    for old_entry in existing_entries:
        matched = False
        new_doi = normalize_doi(new_entry.doi)
        old_doi = normalize_doi(old_entry.doi)
        if new_doi and old_doi and new_doi == old_doi:
            matched = True
        elif title_match_score(new_entry.title, old_entry.title) >= 0.72:
            matched = True

        if not matched:
            continue

        new_entry.source_file_id = old_entry.source_file_id
        if old_entry.reading_status not in ("none",) and new_entry.reading_status == "none":
            new_entry.reading_status = old_entry.reading_status

        if not new_entry.abstract and old_entry.abstract:
            new_entry.abstract = old_entry.abstract
        if not new_entry.doi and old_entry.doi:
            new_entry.doi = old_entry.doi
        if not new_entry.journal and old_entry.journal:
            new_entry.journal = old_entry.journal
        if not new_entry.volume and old_entry.volume:
            new_entry.volume = old_entry.volume
        if not new_entry.issue and old_entry.issue:
            new_entry.issue = old_entry.issue
        if not new_entry.pages and old_entry.pages:
            new_entry.pages = old_entry.pages

        has_job = (
            await db.execute(
                select(Job.id).where(Job.input_file_id == old_entry.source_file_id).limit(1)
            )
        ).scalar_one_or_none()
        has_link = (
            await db.execute(
                select(BibFilterLink.id).where(
                    BibFilterLink.bib_entry_id == old_entry.id
                ).limit(1)
            )
        ).scalar_one_or_none()
        if not has_job and not has_link:
            await db.delete(old_entry)

        break


async def _upsert_bib_entry(
    db,
    owner_user_id: int,
    row: Any,
    source_db: str,
    source_filter_job_id: str | None = None,
    abstract_cn: str | None = None,
) -> BibEntry | None:
    title = clean_nullable_text(row.get("Title")) or "Untitled"
    authors = parse_authors(row.get("Authors"))
    year = parse_year(row.get("Year"))
    doi = clean_nullable_text(row.get("DOI"))
    journal = clean_nullable_text(row.get("Journal"))
    abstract = clean_nullable_text(row.get("Abstract"))
    keywords = parse_keywords(row.get("Keywords"))
    venue_type = clean_nullable_text(row.get("Type"))
    citation_count = parse_int(row.get("Citations"))
    volume = clean_nullable_text(row.get("Volume"))
    issue = clean_nullable_text(row.get("Issue"))
    pages = clean_nullable_text(row.get("Pages"))
    metadata_completeness = compute_metadata_completeness(
        title, authors, year, doi, journal, abstract
    )
    dedup_key = compute_dedup_key(doi, title, authors, year)

    bib_entry = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == owner_user_id,
                BibEntry.dedup_key == dedup_key,
            )
        )
    ).scalar_one_or_none()

    now = utcnow_naive()

    if bib_entry is None:
        bib_entry = BibEntry(
            id=str(uuid.uuid4()),
            owner_user_id=owner_user_id,
            title=title,
            authors_json=json.dumps(authors, ensure_ascii=False),
            year=year,
            doi=doi,
            journal=journal,
            abstract=abstract,
            abstract_cn=abstract_cn,
            keywords_json=json.dumps(keywords, ensure_ascii=False),
            venue_type=venue_type,
            citation_count=citation_count,
            volume=volume,
            issue=issue,
            pages=pages,
            source_db=source_db,
            source_filter_job_id=source_filter_job_id,
            source_file_id=None,
            reading_status="none",
            metadata_completeness=metadata_completeness,
            dedup_key=dedup_key,
            expires_at=None,
        )
        db.add(bib_entry)
        await db.flush()
        return bib_entry

    bib_entry.updated_at = now
    bib_entry.title = title
    bib_entry.authors_json = json.dumps(authors, ensure_ascii=False)
    bib_entry.year = year
    bib_entry.doi = doi
    bib_entry.journal = journal
    bib_entry.abstract = abstract
    if abstract_cn and not bib_entry.abstract_cn:
        bib_entry.abstract_cn = abstract_cn
    bib_entry.keywords_json = json.dumps(keywords, ensure_ascii=False)
    bib_entry.venue_type = venue_type
    bib_entry.citation_count = citation_count
    if not bib_entry.volume and volume:
        bib_entry.volume = volume
    if not bib_entry.issue and issue:
        bib_entry.issue = issue
    if not bib_entry.pages and pages:
        bib_entry.pages = pages
    bib_entry.metadata_completeness = metadata_completeness
    if source_filter_job_id and not bib_entry.source_filter_job_id:
        bib_entry.source_filter_job_id = source_filter_job_id
    return bib_entry


async def persist_filter_results(
    task_id: str,
    user: User,
    file_record: File,
    df,
    out_path: Path,
) -> dict[str, Any]:
    import pandas as pd

    source_db = infer_source_db(df, file_record)
    preview_data = []

    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        if job is None:
            raise RuntimeError("筛选任务不存在。")

        passed_indexes = set(df.index.tolist())
        processed_bibs: dict[str, str] = {}
        now = utcnow_naive()

        for _, row in df.iterrows():
            abstract_cn = clean_nullable_text(row.get("abstract_cn"))
            bib_entry = await _upsert_bib_entry(
                db,
                owner_user_id=user.id,
                row=row,
                source_db=source_db,
                source_filter_job_id=job.id,
                abstract_cn=abstract_cn,
            )
            if bib_entry is None:
                continue

            if bib_entry.expires_at is None:
                bib_entry.expires_at = compute_expires_at(user)

            if bib_entry.id not in processed_bibs:
                await reverse_match_to_existing_files(db, bib_entry, user.id)

            if bib_entry.id in processed_bibs:
                continue

            link = BibFilterLink(
                bib_entry_id=bib_entry.id,
                filter_job_id=job.id,
                passed=1 if row.name in passed_indexes else 0,
                score=float(row["score"]) if "score" in row and pd.notna(row["score"]) else None,
                reason=clean_nullable_text(row.get("reason")),
            )
            db.add(link)
            processed_bibs[bib_entry.id] = bib_entry.id

        artifact_storage_path = build_result_storage_path(out_path)
        artifact = Artifact(
            job_id=job.id,
            owner_user_id=user.id,
            artifact_type="filter_excel",
            filename=out_path.name,
            storage_path=artifact_storage_path,
            size_bytes=out_path.stat().st_size if out_path.exists() else None,
            expires_at=compute_expires_at(user),
        )
        db.add(artifact)

        job.status = "success"
        job.progress = 100
        job.current_stage = "完成"
        job.finished_at = utcnow_naive()
        job.error_msg = None

        await db.commit()

    display_cols = [
        "Title",
        "Authors",
        "Journal",
        "Year",
        "Abstract",
        "abstract_cn",
        "score",
        "reason",
    ]
    final_cols = [c for c in display_cols if c in df.columns]
    if final_cols:
        preview_df = df[final_cols].copy()
        preview_data = preview_df.to_dict("records")
        for row in preview_data:
            for key in list(row.keys()):
                if pd.isna(row[key]):
                    row[key] = None

    return {
        "output_path": artifact_storage_path,
        "row_count": len(df),
        "preview": preview_data,
    }


def run_filter_task(
    task_id: str,
    user_id: int,
    file_id: str,
    file_path: str,
    mode: str,
    topic: str,
    min_year: int,
    keywords: Optional[str],
    prompt_template: str,
    api_key: Optional[str] = None,
):
    """Run filter pipeline in background thread. api_key is REQUIRED."""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def start_job():
            await sync_job_status(
                task_id,
                status="running",
                progress=10,
                current_stage="解析文献题录...",
                started_at=utcnow_naive(),
                error_msg=None,
            )

        loop.run_until_complete(start_job())

        api_key = validate_deepseek_key(api_key)

        tasks[task_id]["owner_user_id"] = user_id
        tasks[task_id]["input_file_id"] = file_id
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "解析文献题录..."
        
        from parsers import get_parser
        from smart_literature_filter import filter_literature, AIEvaluator
        
        # 1. Parse file
        parser = get_parser(file_path)
        if not parser:
            raise ValueError("不支持的文件格式")
        
        parser.parse()
        df = parser.to_dataframe()
        
        tasks[task_id]["progress"] = 25
        tasks[task_id]["stage"] = f"解析完成: {len(df)} 篇文献"
        tasks[task_id]["logs"].append(f"✓ 解析完成: {len(df)} 篇文献")
        
        # 2. Basic filtering
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()] if keywords else None
        df = filter_literature(df, min_year=min_year, keywords=kw_list)
        
        tasks[task_id]["progress"] = 40
        tasks[task_id]["stage"] = f"过滤后: {len(df)} 篇文献"
        tasks[task_id]["logs"].append(f"✓ 过滤后: {len(df)} 篇文献")
        
        if df.empty:
            raise ValueError("过滤后无匹配文献")
        
        # 3. AI Evaluation
        tasks[task_id]["progress"] = 50
        tasks[task_id]["stage"] = "AI 评估中..."
        
        evaluator = AIEvaluator(api_key=api_key)
        ai_results = evaluator.evaluate_batch(df, prompt_template, topic)
        
        tasks[task_id]["progress"] = 80
        tasks[task_id]["stage"] = f"AI 评估完成: {len(ai_results)} 篇"
        tasks[task_id]["logs"].append(f"✓ AI 评估完成: {len(ai_results)} 篇")
        
        # 4. Export
        import pandas as pd
        ai_df = pd.DataFrame(ai_results)
        if not ai_df.empty and "original_index" in ai_df.columns:
            ai_df.set_index("original_index", inplace=True)
            df = df.join(ai_df, how="left")
            if "score" in df.columns:
                df["score"] = pd.to_numeric(df["score"], errors="coerce")
                df = df.sort_values(by="score", ascending=False)
        
        user_results_dir = get_filter_results_dir(user_id, task_id)
        out_path = user_results_dir / f"filtered_{mode}_{task_id}.xlsx"
        display_cols = [
            "Title",
            "Authors",
            "Journal",
            "Year",
            "DOI",
            "Abstract",
            "abstract_cn",
            "score",
            "reason",
        ]
        final_cols = [c for c in display_cols if c in df.columns]
        df_display = df[final_cols].copy()
        # Clean control characters before writing to Excel
        for col in df_display.columns:
            if pd.api.types.is_string_dtype(df_display[col]):
                df_display[col] = df_display[col].apply(_clean_for_excel)
        df_display.to_excel(out_path, index=False, engine="openpyxl")

        async def finalize_success():
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                file_record = await db.get(File, file_id)
                if user is None or file_record is None:
                    raise RuntimeError("任务依赖的用户或文件不存在。")
            result = await persist_filter_results(task_id, user, file_record, df, out_path)
            return result

        result = loop.run_until_complete(finalize_success())
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append(f"✓ 已导出: {out_path.name}")
        tasks[task_id]["result"] = result
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ 错误: {str(e)}")
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["error"] = str(e)

        async def finalize_failure():
            await sync_job_status(
                task_id,
                status="failed",
                current_stage=f"错误: {str(e)}",
                error_msg=str(e),
                finished_at=utcnow_naive(),
            )

        try:
            loop.run_until_complete(finalize_failure())
        except Exception:
            pass
    finally:
        loop.close()


@router.post("/start")
async def start_filter(
    request: FilterRequest,
    user: User = Depends(current_user),
    db=Depends(get_db),
):
    """Start literature filtering task"""
    # Validate mode
    if request.mode not in ("explorer", "reviewer", "empiricist"):
        raise HTTPException(status_code=400, detail="Invalid mode")
    
    # Validate topic
    if not request.topic or not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic is required")
    
    # Find file
    file_record = (
        await db.execute(
            select(File).where(File.id == request.file_id, File.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if file_record.file_type not in {"bibliography", "txt"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="筛选仅支持题录文件。",
        )
    prompt_template = await get_effective_prompt_text(
        db,
        user_id=user.id,
        prompt_type="filter",
        prompt_key=request.mode,
    )

    file_path = get_file_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    
    # Create task
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "id": task_id,
        "owner_user_id": user.id,
        "type": "filter",
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "result": None,
        "error": None
    }

    job = Job(
        id=task_id,
        owner_user_id=user.id,
        job_type="filter",
        status="pending",
        input_file_id=file_record.id,
        params_json=json.dumps(
            {
                "mode": request.mode,
                "topic": request.topic,
                "min_year": request.min_year,
                "keywords": request.keywords,
            },
            ensure_ascii=False,
        ),
        progress=0,
        current_stage="等待开始...",
        expires_at=compute_expires_at(user),
    )
    db.add(job)
    await db.commit()
    
    # Start background thread
    thread = threading.Thread(
        target=run_filter_task,
        args=(
            task_id,
            user.id,
            file_record.id,
            file_path,
            request.mode,
            request.topic,
            request.min_year,
            request.keywords,
            prompt_template,
            request.api_key,
        ),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}/status")
async def get_task_status(
    task_id: str,
    user: User = Depends(current_user),
    db=Depends(get_db),
):
    """Get task status"""
    job = (
        await db.execute(select(Job).where(Job.id == task_id, Job.owner_user_id == user.id))
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    runtime = tasks.get(task_id)
    if runtime is not None:
        return runtime

    response = {
        "id": job.id,
        "type": "filter",
        "status": "completed" if job.status == "success" else job.status,
        "progress": job.progress,
        "stage": job.current_stage or "处理中...",
        "logs": [],
        "result": None,
        "error": job.error_msg,
    }

    if job.status == "success":
        artifact = (
            await db.execute(
                select(Artifact).where(
                    Artifact.job_id == job.id, Artifact.artifact_type == "filter_excel"
                )
            )
        ).scalar_one_or_none()
        links = (
            await db.execute(
                select(BibFilterLink, BibEntry)
                .join(BibEntry, BibEntry.id == BibFilterLink.bib_entry_id)
                .where(BibFilterLink.filter_job_id == job.id, BibFilterLink.passed == 1)
            )
        ).all()
        preview = []
        for link, bib_entry in links:
            preview.append(
                {
                    "Title": bib_entry.title,
                    "Authors": "; ".join(json.loads(bib_entry.authors_json or "[]")),
                    "Journal": bib_entry.journal,
                    "Year": bib_entry.year,
                    "score": link.score,
                    "reason": link.reason,
                }
            )
        response["result"] = {
            "output_path": artifact.storage_path if artifact else None,
            "row_count": len(preview),
            "preview": preview,
        }

    return response


@router.post("/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: User = Depends(current_user),
    db=Depends(get_db),
):
    """Cancel task (best effort)"""
    job = (
        await db.execute(select(Job).where(Job.id == task_id, Job.owner_user_id == user.id))
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if task_id in tasks:
        tasks[task_id]["status"] = "cancelled"
        tasks[task_id]["stage"] = "已取消"
        tasks[task_id]["error"] = None

    job.status = "canceled"
    job.current_stage = "已取消"
    job.error_msg = None
    job.finished_at = utcnow_naive()
    await db.commit()
    return {"success": True}


class DirectImportRequest(BaseModel):
    file_id: str


class DirectImportEntrySummary(BaseModel):
    title: str
    authors: list[str]
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None


class DirectImportResponse(BaseModel):
    count: int
    entries: list[DirectImportEntrySummary]


@router.post("/direct-import")
async def direct_import(
    req: DirectImportRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = (
        await db.execute(
            select(File).where(File.id == req.file_id, File.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    file_path = lookup_path_by_file_id(req.file_id)
    if file_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found on disk")

    parser = get_parser(str(file_path))
    if parser is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format",
        )

    parser.parse()
    df = parser.to_dataframe()

    source_db_map = {"WoS": "wos", "CNKI": "cnki"}
    raw_source = infer_source_db(df, file_record)
    source_db = raw_source if raw_source in ("wos", "cnki") else "other"

    imported: list[DirectImportEntrySummary] = []
    for _, row in df.iterrows():
        bib_entry = await _upsert_bib_entry(
            db,
            owner_user_id=user.id,
            row=row,
            source_db=source_db,
        )
        if bib_entry is None:
            continue

        if bib_entry.expires_at is None:
            bib_entry.expires_at = compute_expires_at(user)

        is_new = bib_entry.source_file_id is None
        if is_new:
            await reverse_match_to_existing_files(db, bib_entry, user.id)

        await db.flush()

        authors_list = json.loads(bib_entry.authors_json or "[]")
        imported.append(
            DirectImportEntrySummary(
                title=bib_entry.title,
                authors=authors_list,
                year=bib_entry.year,
                doi=bib_entry.doi,
                journal=bib_entry.journal,
            )
        )

    await db.commit()

    return DirectImportResponse(count=len(imported), entries=imported)
