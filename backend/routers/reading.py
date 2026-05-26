"""Reading Router - authenticated reading jobs with DB persistence."""
import logging
import traceback
import os
import sys
import uuid
import threading
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from services.deepseek_limiter import deepseek_semaphore
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path)

from backend.utils.api_key import validate_deepseek_key

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import AsyncSessionLocal, get_db
from db.models import Artifact, BibEntry, BibReference, File, Job, JobBibEntry, ReadingItem, User
from db.utils import compute_dedup_key, title_match_score
from backend.routers.metadata_extractor import build_frontmatter
from services.pdf_metadata_extract import extract_front_matter
from services.pdf_metadata_llm import extract_metadata_with_llm
from prompt_service import get_effective_prompt_map
from result_storage import build_result_storage_path, get_results_root, resolve_result_path
from upload_storage import lookup_original_name, lookup_path_by_file_id
from services.queue_manager import task_queue

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

RESULTS_ROOT = get_results_root()

LONG_DIMENSION_KEYS = {
    "研究问题": "long.research_question",
    "理论框架": "long.theory_framework",
    "识别策略": "long.identification_strategy",
    "数据来源": "long.data_source",
    "变量度量": "long.variable_measurement",
    "识别假设": "long.identification_assumptions",
    "统计结果": "long.statistical_results",
    "机制分析": "long.mechanism_analysis",
    "稳健性检验": "long.robustness_checks",
    "外部有效性": "long.external_validity",
    "贡献与局限": "long.contributions_limitations",
    "写作质量": "long.writing_quality",
    "自定义问题": "long.custom_question",
}

QUANT_STEP_KEYS = {
    "第一步：核心贡献识别": "quant.step1",
    "第二步：理论框架评估": "quant.step2",
    "第三步：方法论批判": "quant.step3",
    "第四步：实证结果解读": "quant.step4",
    "第五步：局限性分析": "quant.step5",
    "第六步：实践意义": "quant.step6",
    "第七步：未来方向": "quant.step7",
}

QUAL_STEP_KEYS = {
    "第一步：背景与问题": "qual.step1",
    "第二步：理论视角": "qual.step2",
    "第三步：逻辑与证据": "qual.step3",
    "第四步：价值与启示": "qual.step4",
}

QUANT_PROMPT_KEYS = {
    "第一步：核心贡献识别": "step_1",
    "第二步：理论框架评估": "step_2",
    "第三步：方法论批判": "step_3",
    "第四步：实证结果解读": "step_4",
    "第五步：局限性分析": "step_5",
    "第六步：实践意义": "step_6",
    "第七步：未来方向": "step_7",
}

QUAL_PROMPT_KEYS = {
    "第一步：背景与问题": "L1",
    "第二步：理论视角": "L2",
    "第三步：逻辑与证据": "L3",
    "第四步：价值与启示": "L4",
}


def normalize_reading_prompt(content: str) -> str:
    text = (content or "").strip()
    if not text:
        text = "请分析这个维度。"
    if "寒暄" not in text and "客套" not in text:
        text += '\n\n# 重要\n直接输出分析内容，不要"好的""我将""作为..."等客套开场白。'
    return text


def slugify_key_fragment(value: str) -> str:
    text = re.sub(r"\s+", "_", value.strip().lower())
    text = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "item"


def parse_markdown_numbered_sections(content: str, level: int) -> list[dict]:
    if not content.strip():
        return []

    if level == 3:
        pattern = re.compile(r"^###\s*\*\*(\d+)\.\s*(.+?)\*\*\s*$", re.MULTILINE)
    else:
        pattern = re.compile(r"^##\s*(\d+)\.\s*(.+?)\s*$", re.MULTILINE)

    matches = list(pattern.finditer(content))
    if not matches:
        return []

    sections: list[dict] = []
    for index, match in enumerate(matches):
        section_start = match.end()
        section_end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[section_start:section_end].strip()
        title = match.group(2).strip()
        number = int(match.group(1))
        sections.append(
            {
                "number": number,
                "title": title,
                "content": body,
            }
        )
    return sections


def build_long_reading_items(results: dict[str, str], custom_question: Optional[str] = None) -> list[dict]:
    items: list[dict] = []
    sort_order = 0
    for label, content in results.items():
        section_type = "custom" if label == "自定义问题" else "dimension"
        item_key = LONG_DIMENSION_KEYS.get(label)
        if item_key is None:
            item_key = f"long.{slugify_key_fragment(label)}"
        item_label = label if label != "自定义问题" or not custom_question else f"自定义问题：{custom_question.strip()}"
        items.append(
            {
                "mode": "long",
                "section_type": section_type,
                "parent_key": None,
                "item_key": item_key,
                "item_label": item_label,
                "sort_order": sort_order,
                "content": str(content).strip(),
            }
        )
        sort_order += 1
    return items


def build_step_reading_items(results: dict[str, str], *, mode: str) -> list[dict]:
    items: list[dict] = []
    step_keys = QUANT_STEP_KEYS if mode == "quant" else QUAL_STEP_KEYS
    heading_level = 3 if mode == "quant" else 2

    for step_index, (step_label, content) in enumerate(results.items(), start=1):
        step_key = step_keys.get(step_label, f"{mode}.step{step_index}")
        text = str(content).strip()
        items.append(
            {
                "mode": mode,
                "section_type": "step",
                "parent_key": None,
                "item_key": step_key,
                "item_label": step_label,
                "sort_order": step_index * 100,
                "content": text,
            }
        )

        for section_index, section in enumerate(parse_markdown_numbered_sections(text, heading_level), start=1):
            number = section["number"]
            title = section["title"]
            section_key = f"{step_key}.q{number}"
            items.append(
                {
                    "mode": mode,
                    "section_type": "subquestion",
                    "parent_key": step_key,
                    "item_key": section_key,
                    "item_label": f"{number}. {title}",
                    "sort_order": step_index * 100 + section_index,
                    "content": section["content"] or text,
                }
            )

    return items


# In-memory task store
tasks = {}


class LongContextRequest(BaseModel):
    file_id: str
    analysis_dims: list[str]
    custom_question: Optional[str] = None
    extraction_method: str = "full"
    api_key: Optional[str] = None
    force_overwrite: Optional[bool] = None
    conflict_resolution: Optional[str] = None
    dimension_set_id: Optional[int] = None


class SimpleReadingRequest(BaseModel):
    file_id: str
    api_key: Optional[str] = None
    force_overwrite: Optional[bool] = None
    conflict_resolution: Optional[str] = None


class BatchReadingRequest(BaseModel):
    file_ids: list[str]
    mode: str
    analysis_dims: Optional[list[str]] = None
    custom_question: Optional[str] = None
    extraction_method: str = "full"
    api_key: Optional[str] = None
    force_overwrite: Optional[bool] = None
    conflict_resolution: Optional[str] = None
    dimension_set_id: Optional[int] = None


class CheckConflictRequest(BaseModel):
    file_id: str
    mode: str
    analysis_dims: Optional[list[str]] = None


class BatchCheckConflictRequest(BaseModel):
    file_ids: list[str]
    mode: str
    analysis_dims: Optional[list[str]] = None


def resolve_conflict_mode(force_overwrite: Optional[bool], conflict_resolution: Optional[str], default: str = "check") -> str:
    if conflict_resolution in ("overwrite", "new", "incremental", "skip"):
        return conflict_resolution
    if force_overwrite is True:
        return "overwrite"
    return default


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compute_expires_at(user: User) -> datetime | None:
    if user.role == "normal":
        return utcnow_naive() + timedelta(hours=24)
    return None


def get_results_dir(user_id: int, job_id: str) -> Path:
    result_dir = RESULTS_ROOT / str(user_id) / job_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def infer_bib_source_db(file_record: File) -> str:
    return "md_extracted" if file_record.file_type == "markdown" else "pdf_extracted"


async def get_file_record(db: AsyncSession, user: User, file_id: str) -> File:
    record = (
        await db.execute(select(File).where(File.id == file_id, File.owner_user_id == user.id))
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return record


def extract_paper_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".md", ".markdown"}:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    from extractor import PDFExtractor
    return PDFExtractor().extract_content(file_path) or ""


def ensure_readable_file_type(file_record: File) -> None:
    if file_record.file_type not in {"pdf", "markdown"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="精读仅支持 PDF 或 Markdown 文件。",
        )


async def get_or_create_bib_entry(db: AsyncSession, user: User, file_record: File) -> BibEntry:
    existing = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == user.id,
                BibEntry.source_file_id == file_record.id,
            ).limit(1)
        )
    ).scalars().first()
    if existing is not None:
        if file_record.file_type == "markdown" and not existing.markdown_source_file_id:
            existing.markdown_source_file_id = file_record.id
        if existing.reading_status == "none":
            existing.reading_status = "has_pdf"
        return existing

    original_name = file_record.original_name or file_record.id
    title = os.path.splitext(original_name)[0]
    dedup_key = compute_dedup_key(None, title, [], None)

    candidates = (
        await db.execute(
            select(BibEntry).where(BibEntry.owner_user_id == user.id).order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc())
        )
    ).scalars().all()

    existing_by_title = (
        next((candidate for candidate in candidates if candidate.dedup_key == dedup_key), None)
    )
    if existing_by_title is None:
        best_score = 0.0
        best_entry: BibEntry | None = None
        for candidate in candidates:
            score = title_match_score(title, candidate.title or "")
            if score > best_score:
                best_score = score
                best_entry = candidate
        if best_entry is not None and best_score >= 0.72:
            existing_by_title = best_entry

    if existing_by_title is not None:
        if file_record.file_type == "markdown" and not existing_by_title.markdown_source_file_id:
            existing_by_title.markdown_source_file_id = file_record.id
        if not existing_by_title.source_file_id:
            existing_by_title.source_file_id = file_record.id
        if existing_by_title.reading_status == "none":
            existing_by_title.reading_status = "has_pdf"
        return existing_by_title

    bib_entry = BibEntry(
        id=str(uuid.uuid4()),
        owner_user_id=user.id,
        title=title or file_record.id,
        authors_json="[]",
        year=None,
        doi=None,
        journal=None,
        abstract=None,
        keywords_json="[]",
        venue_type=None,
        citation_count=None,
        source_db=infer_bib_source_db(file_record),
        source_filter_job_id=None,
        source_file_id=file_record.id,
        markdown_source_file_id=file_record.id if file_record.file_type == "markdown" else None,
        user_tags_json="[]",
        user_note=None,
        is_pinned=0,
        reading_status="has_pdf",
        metadata_completeness="minimal",
        dedup_key=dedup_key,
        expires_at=compute_expires_at(user),
    )
    db.add(bib_entry)
    await db.flush()
    return bib_entry


async def create_reading_job(
    db: AsyncSession,
    user: User,
    file_record: File,
    bib_entry: BibEntry,
    job_type: str,
    params: dict,
) -> str:
    task_id = str(uuid.uuid4())
    job = Job(
        id=task_id,
        owner_user_id=user.id,
        job_type=job_type,
        status="pending",
        input_file_id=file_record.id,
        params_json=json.dumps(params, ensure_ascii=False),
        progress=0,
        current_stage="等待开始...",
        expires_at=compute_expires_at(user),
    )
    db.add(job)
    db.add(
        JobBibEntry(
            job_id=task_id,
            bib_entry_id=bib_entry.id,
            role="target",
            sort_order=0,
        )
    )
    return task_id


async def find_existing_reading_job(db: AsyncSession, bib_entry_id: str, job_type: str) -> Job | None:
    return (
        await db.execute(
            select(Job)
            .join(JobBibEntry, JobBibEntry.job_id == Job.id)
            .where(
                JobBibEntry.bib_entry_id == bib_entry_id,
                Job.job_type == job_type,
                Job.status == "success",
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )
    ).scalars().first()


def check_reading_duplicate(bib_entry: BibEntry, force_overwrite: bool) -> Optional[dict]:
    if bib_entry.reading_status not in ("reading", "read"):
        return None
    if force_overwrite:
        return None
    return {
        "detail": "already_read",
        "bib_entry": {
            "id": bib_entry.id,
            "title": bib_entry.title,
            "reading_status": bib_entry.reading_status,
        },
    }


@router.post("/check-conflict")
async def check_conflict(
    request: CheckConflictRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = await get_file_record(db, user, request.file_id)
    ensure_readable_file_type(file_record)
    bib_entry = await get_or_create_bib_entry(db, user, file_record)

    job_type_map = {"long": "reading_long", "quant": "reading_quant", "qual": "reading_qual"}
    job_type = job_type_map.get(request.mode)
    if not job_type:
        raise HTTPException(status_code=400, detail="mode 必须是 long/quant/qual")

    existing_jobs = (
        await db.execute(
            select(Job)
            .join(JobBibEntry, JobBibEntry.job_id == Job.id)
            .where(
                JobBibEntry.bib_entry_id == bib_entry.id,
                Job.job_type == job_type,
                Job.status == "success",
            )
            .order_by(Job.created_at.desc())
        )
    ).scalars().all()

    if not existing_jobs:
        return {"has_conflict": False}

    latest = existing_jobs[0]
    dimensions: list[str] = []
    incremental_dims: list[str] = []

    if request.analysis_dims and job_type == "reading_long":
        existing_items = (
            await db.execute(
                select(ReadingItem)
                .where(
                    ReadingItem.job_id == latest.id,
                    ReadingItem.section_type.in_(["dimension", "custom"]),
                )
                .order_by(ReadingItem.sort_order)
            )
        ).scalars().all()
        dimensions = [it.item_label for it in existing_items]
        existing_keys = {it.item_key for it in existing_items}
        incremental_dims = [
            d for d in request.analysis_dims
            if LONG_DIMENSION_KEYS.get(d, f"long.{slugify_key_fragment(d)}") not in existing_keys
            and d not in dimensions
        ]

    return {
        "has_conflict": True,
        "bib_entry": {
            "id": bib_entry.id,
            "title": bib_entry.title,
            "reading_status": bib_entry.reading_status,
        },
        "existing_job": {
            "job_id": latest.id,
            "job_type": latest.job_type,
            "created_at": latest.created_at.isoformat() if latest.created_at else None,
            "dimensions": dimensions,
            "mode_label": {
                "reading_long": "长文本精读",
                "reading_quant": "七步精读",
                "reading_qual": "四步精读",
            }.get(latest.job_type, latest.job_type),
        },
        "incremental_dims": incremental_dims,
    }


async def cleanup_old_reading_data(db: AsyncSession, bib_entry: BibEntry, job_type: str | None = None) -> None:
    query = (
        select(JobBibEntry.job_id)
        .join(Job, Job.id == JobBibEntry.job_id)
        .where(JobBibEntry.bib_entry_id == bib_entry.id)
    )
    if job_type is not None:
        query = query.where(Job.job_type == job_type)
    old_job_ids = (await db.execute(query)).scalars().all()

    if old_job_ids:
        old_artifacts = (
            await db.execute(select(Artifact).where(Artifact.job_id.in_(old_job_ids)))
        ).scalars().all()
        for art in old_artifacts:
            if art.storage_path:
                physical = resolve_result_path(art.storage_path)
                if physical.exists():
                    try:
                        physical.unlink()
                    except OSError:
                        pass
        await db.execute(delete(Artifact).where(Artifact.job_id.in_(old_job_ids)))
        await db.execute(delete(ReadingItem).where(ReadingItem.job_id.in_(old_job_ids)))
        await db.execute(delete(JobBibEntry).where(JobBibEntry.job_id.in_(old_job_ids)))
        await db.execute(delete(Job).where(Job.id.in_(old_job_ids)))

    remaining_jobs = (
        await db.execute(
            select(JobBibEntry.job_id)
            .join(Job, Job.id == JobBibEntry.job_id)
            .where(JobBibEntry.bib_entry_id == bib_entry.id)
        )
    ).scalars().all()

    if not remaining_jobs:
        await db.execute(delete(ReadingItem).where(ReadingItem.bib_entry_id == bib_entry.id))
        bib_entry.reading_status = "has_pdf"
    await db.flush()


def init_task_payload(task_id: str, task_type: str, user_id: int, file_id: str, bib_entry_id: str) -> dict:
    return {
        "id": task_id,
        "owner_user_id": user_id,
        "input_file_id": file_id,
        "bib_entry_id": bib_entry_id,
        "type": task_type,
        "status": "queued",
        "progress": 0,
        "stage": "等待开始...",
        "logs": [],
        "result": None,
        "error": None,
        "created_at": utcnow_naive(),
    }


async def sync_job_and_bib_start(task_id: str, bib_entry_id: str, *, stage: str, progress: int) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        bib_entry = await db.get(BibEntry, bib_entry_id)
        if job is not None:
            job.status = "running"
            job.progress = progress
            job.current_stage = stage
            job.error_msg = None
            job.started_at = utcnow_naive()
        if bib_entry is not None:
            bib_entry.reading_status = "reading"
            bib_entry.updated_at = utcnow_naive()
        await db.commit()


async def finalize_reading_success(
    task_id: str,
    bib_entry_id: str,
    user_id: int,
    artifact_files: list[dict],
    reading_items: Optional[list[dict]] = None,
) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        bib_entry = await db.get(BibEntry, bib_entry_id)
        owner = await db.get(User, user_id)
        if job is None or bib_entry is None or owner is None:
            return

        for sort_order, artifact_info in enumerate(artifact_files):
            absolute_path = Path(artifact_info["absolute_path"])
            artifact = Artifact(
                job_id=task_id,
                owner_user_id=user_id,
                artifact_type=artifact_info["artifact_type"],
                filename=absolute_path.name,
                storage_path=build_result_storage_path(absolute_path),
                size_bytes=absolute_path.stat().st_size if absolute_path.exists() else None,
                sort_order=sort_order,
                expires_at=compute_expires_at(owner),
            )
            db.add(artifact)

        for item in reading_items or []:
            db.add(
                ReadingItem(
                    owner_user_id=user_id,
                    bib_entry_id=bib_entry_id,
                    job_id=task_id,
                    mode=item["mode"],
                    section_type=item["section_type"],
                    parent_key=item.get("parent_key"),
                    item_key=item["item_key"],
                    item_label=item["item_label"],
                    sort_order=item.get("sort_order", 0),
                    content=item["content"],
                )
            )

        job.status = "success"
        job.progress = 100
        job.current_stage = "完成"
        job.error_msg = None
        job.finished_at = utcnow_naive()
        bib_entry.reading_status = "read"
        bib_entry.updated_at = utcnow_naive()
        await db.commit()


async def finalize_reading_failure(task_id: str, bib_entry_id: str, error_message: str, *, canceled: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, task_id)
        bib_entry = await db.get(BibEntry, bib_entry_id)
        if job is not None:
            job.status = "canceled" if canceled else "failed"
            job.current_stage = "已取消" if canceled else f"错误: {error_message}"
            job.error_msg = None if canceled else error_message
            job.finished_at = utcnow_naive()
        if bib_entry is not None:
            bib_entry.reading_status = "has_pdf"
            bib_entry.updated_at = utcnow_naive()
        await db.commit()


async def _try_update_bib_metadata(
    bib_entry_id: str,
    file_path: str,
    original_name: str,
    api_key: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> list[str]:
    """从PDF前三页提取元数据并更新BibEntry。只补空字段，标题如果是文件名则替换。
    返回被更新的字段名列表。"""
    try:
        from pathlib import Path
        from db.utils import compute_dedup_key

        if metadata is None:
            front_matter = extract_front_matter(file_path)
            if not front_matter.get("page_1_full"):
                return []

            metadata = extract_metadata_with_llm(
                front_matter,
                original_name,
                api_key=api_key,
            )
        if not metadata or metadata.get("confidence", 0) < 0.3:
            return []

        async with AsyncSessionLocal() as db:
            bib_entry = await db.get(BibEntry, bib_entry_id)
            if bib_entry is None:
                return []

            updated_fields = []

            # Title: 如果当前标题是文件名，允许替换
            current_title = (bib_entry.title or "").strip()
            extracted_title = (metadata.get("title") or "").strip()
            if extracted_title:
                is_filename_like = current_title == original_name or current_title == os.path.splitext(original_name)[0]
                if not current_title or is_filename_like:
                    bib_entry.title = extracted_title
                    updated_fields.append("title")

            # Authors
            current_authors = json.loads(bib_entry.authors_json) if bib_entry.authors_json else []
            extracted_authors = metadata.get("authors", [])
            if extracted_authors and not current_authors:
                bib_entry.authors_json = json.dumps(extracted_authors, ensure_ascii=False)
                updated_fields.append("authors")

            # Year
            if metadata.get("year") and bib_entry.year is None:
                bib_entry.year = metadata["year"]
                updated_fields.append("year")

            # Journal
            if metadata.get("journal") and not (bib_entry.journal or "").strip():
                bib_entry.journal = metadata["journal"]
                updated_fields.append("journal")

            # DOI
            if metadata.get("doi") and not (bib_entry.doi or "").strip():
                bib_entry.doi = metadata["doi"]
                updated_fields.append("doi")

            # Abstract
            if metadata.get("abstract") and not (bib_entry.abstract or "").strip():
                bib_entry.abstract = metadata["abstract"]
                updated_fields.append("abstract")

            # Keywords
            current_kw = json.loads(bib_entry.keywords_json) if bib_entry.keywords_json else []
            extracted_kw = metadata.get("keywords", [])
            if extracted_kw and not current_kw:
                bib_entry.keywords_json = json.dumps(extracted_kw, ensure_ascii=False)
                updated_fields.append("keywords")

            # Volume / Issue / Pages
            for field in ["volume", "issue", "pages"]:
                if metadata.get(field) and not getattr(bib_entry, field, None):
                    setattr(bib_entry, field, metadata[field])
                    updated_fields.append(field)

            language = metadata.get("language")
            if language in {"en", "zh"} and not bib_entry.language:
                bib_entry.language = language
                updated_fields.append("language")

            # Recompute dedup_key
            authors_list = json.loads(bib_entry.authors_json) if bib_entry.authors_json else []
            bib_entry.dedup_key = compute_dedup_key(
                bib_entry.doi, bib_entry.title, authors_list, bib_entry.year
            )

            # Recompute metadata_completeness
            has_title = bool((bib_entry.title or "").strip())
            has_authors = bool(authors_list)
            has_year = bib_entry.year is not None
            has_doi = bool((bib_entry.doi or "").strip())
            has_journal = bool((bib_entry.journal or "").strip())
            has_abstract = bool((bib_entry.abstract or "").strip())
            if has_title and has_authors and has_year and has_doi and has_journal and has_abstract:
                bib_entry.metadata_completeness = "full"
            elif has_title and has_authors:
                bib_entry.metadata_completeness = "partial"
            else:
                bib_entry.metadata_completeness = "minimal"

            bib_entry.updated_at = utcnow_naive()
            await db.commit()
            return updated_fields

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.warning("Metadata extraction/update failed for bib_entry %s: %s", bib_entry_id, e, exc_info=True)
        return []


async def build_task_status_from_db(task_id: str, user_id: int) -> dict | None:
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
        final_artifact = next((item for item in artifacts if item.artifact_type == "reading_final"), None)

        return {
            "id": job.id,
            "owner_user_id": user_id,
            "type": job.job_type,
            "status": "completed" if job.status == "success" else job.status,
            "progress": job.progress,
            "stage": job.current_stage or "处理中...",
            "logs": [],
            "result": {
                "output_path": final_artifact.storage_path if final_artifact else None,
                "artifacts": [
                    {
                        "artifact_type": artifact.artifact_type,
                        "filename": artifact.filename,
                        "storage_path": artifact.storage_path,
                    }
                    for artifact in artifacts
                ],
            }
            if artifacts
            else None,
            "error": job.error_msg,
        }


def get_file_path(file_id: str) -> Optional[str]:
    path = lookup_path_by_file_id(file_id)
    return str(path) if path is not None else None


def get_original_filename(file_path: str) -> str:
    """Get original uploaded filename from DB record when available."""
    file_id = os.path.splitext(os.path.basename(file_path))[0]
    original_name = lookup_original_name(file_id)
    if original_name:
        return original_name
    return os.path.splitext(os.path.basename(file_path))[0]


def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem"""
    # Remove extension
    name = os.path.splitext(name)[0]
    # Replace invalid chars
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name


def _try_extract_references(
    file_path: str,
    user_id: int,
    task_id: str,
    source_title: str,
    bib_entry_id: str,
    api_key: Optional[str] = None,
) -> list[dict] | None:
    """Try to extract references during reading.
    Returns artifact files on success, empty list on failure, None if skipped (already exists)."""
    try:
        from routers.references import write_trace_outputs, persist_trace_success
        from services.deepseek_refs import extract_references_deepseek, trace_citations_deepseek

        import asyncio
        from db import AsyncSessionLocal

        async def _has_existing_refs() -> bool:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(BibReference.id).where(
                        BibReference.source_bib_entry_id == bib_entry_id
                    ).limit(1)
                )
                return result.scalar_one_or_none() is not None

        if asyncio.run(_has_existing_refs()):
            logger = logging.getLogger(__name__)
            logger.info("References already exist for bib_entry %s, skipping extraction", bib_entry_id)
            return None

        references = extract_references_deepseek(file_path, api_key=api_key)
        if not references:
            logger = logging.getLogger(__name__)
            logger.warning("Reference extraction returned 0 refs for task %s", task_id)
            return []

        references = trace_citations_deepseek(file_path, references, api_key=api_key)

        for ref in references:
            ref["dedup_key"] = compute_dedup_key(
                ref.get("doi"), ref.get("title") or ref.get("raw_text", "")[:80],
                ref.get("authors", []), ref.get("year"),
            )
            ref.setdefault("citations", [])

        artifact_files = write_trace_outputs(user_id, task_id, source_title, references)

        ref_task_id = str(uuid.uuid4())
        asyncio.run(_create_ref_trace_job_and_persist(
            ref_task_id, user_id, bib_entry_id, references, artifact_files,
        ))

        return artifact_files
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error("Reference extraction during reading failed for task %s: %s", task_id, e, exc_info=True)
        return []


async def _create_ref_trace_job_and_persist(
    ref_task_id: str,
    user_id: int,
    bib_entry_id: str,
    references: list[dict],
    artifact_files: list[dict],
) -> None:
    """Create a reference_trace job and persist references to database."""
    from routers.references import persist_trace_success

    async with AsyncSessionLocal() as db:
        owner = await db.get(User, user_id)
        if owner is None:
            return

        # Create a reference_trace type job
        job = Job(
            id=ref_task_id,
            owner_user_id=user_id,
            job_type="reference_trace",
            status="pending",
            progress=0,
            current_stage="等待开始...",
            expires_at=compute_expires_at(owner),
        )
        db.add(job)

        # Link job to bib_entry as reference_source
        db.add(
            JobBibEntry(
                job_id=ref_task_id,
                bib_entry_id=bib_entry_id,
                role="reference_source",
                sort_order=0,
            )
        )
        await db.commit()

    # Now persist the references using the existing function
    await persist_trace_success(ref_task_id, user_id, bib_entry_id, references, artifact_files)


def _clean_for_excel(text):
    """Remove control characters that Excel cannot handle."""
    if not isinstance(text, str):
        return text
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)


def _is_empty_result(content: str, min_chars: int = 50) -> bool:
    if not content or not content.strip():
        return True
    stripped = content.strip()
    if stripped.startswith("[分析出错"):
        return True
    if len(stripped) < min_chars and not any(c in stripped for c in "。；：？！\n"):
        return True
    return False


def _check_and_retry_empty_dimensions(
    results: dict[str, str],
    task_id: str,
    retry_fn,
    max_retries: int = 2,
) -> dict[str, str]:
    for attempt in range(1, max_retries + 1):
        empty_keys = [k for k, v in results.items() if _is_empty_result(v)]
        if not empty_keys:
            break
        tasks[task_id]["logs"].append(
            f"[后检查] 第 {attempt} 次重试：{len(empty_keys)} 个维度需要重新分析"
        )

        def _retry_one(key):
            if tasks[task_id].get("status") == "cancelled":
                return key, None, "cancelled"
            try:
                new_content = retry_fn(key)
                return key, new_content, None
            except Exception as e:
                return key, None, str(e)

        with ThreadPoolExecutor(max_workers=min(len(empty_keys), 6)) as pool:
            retry_futures = {pool.submit(_retry_one, k): k for k in empty_keys}
            for future in as_completed(retry_futures):
                if tasks[task_id].get("status") == "cancelled":
                    return results
                key, new_content, err = future.result()
                if err == "cancelled":
                    return results
                if new_content and not _is_empty_result(new_content):
                    results[key] = new_content
                    tasks[task_id]["logs"].append(f"✓ [重试] {key} 完成")
                elif err:
                    tasks[task_id]["logs"].append(f"⚠ [重试] {key} 失败: {str(err)[:80]}")
                else:
                    tasks[task_id]["logs"].append(f"⚠ [重试] {key} 仍为空")
    still_empty = [k for k, v in results.items() if _is_empty_result(v)]
    if still_empty:
        tasks[task_id]["logs"].append(
            f"⚠ [后检查] {len(still_empty)} 个维度重试后仍为空: {', '.join(still_empty[:5])}"
        )
    else:
        tasks[task_id]["logs"].append("✓ [后检查] 所有维度检查通过")
    return results


async def _query_prev_reading_jobs(user_id: int, bib_entry_id: str, job_type: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Job.id)
                .join(JobBibEntry, JobBibEntry.job_id == Job.id)
                .where(
                    JobBibEntry.bib_entry_id == bib_entry_id,
                    Job.job_type == job_type,
                    Job.status == "success",
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalars().all()
        return list(rows)


async def _query_prev_reading_items(job_id: str) -> list[ReadingItem]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(ReadingItem).where(ReadingItem.job_id == job_id).order_by(ReadingItem.sort_order)
                )
            ).scalars().all()
        )


def run_long_context_task(
    task_id: str,
    user_id: int,
    bib_entry_id: str,
    file_path: str,
    analysis_dims: list,
    custom_question: Optional[str],
    extraction_method: str,
    prompt_overrides: dict[str, str],
    api_key: Optional[str] = None,
    dimension_set_id: Optional[int] = None,
    conflict_resolution: Optional[str] = None,
):
    """Run long context analysis in background thread. api_key is REQUIRED."""
    try:
        import asyncio

        task_queue.mark_running(task_id)
        asyncio.run(sync_job_and_bib_start(task_id, bib_entry_id, stage="提取文本...", progress=10))
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取文本..."
        tasks[task_id]["logs"].append("[阶段 1/3] 提取文本...")
        
        api_key = validate_deepseek_key(api_key)
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(api_key)
        
        # 3. Read file text and create cache
        tasks[task_id]["progress"] = 20
        tasks[task_id]["stage"] = "读取论文内容..."
        tasks[task_id]["logs"].append("[阶段 2/3] 读取论文内容...")
        
        paper_text = extract_paper_text(file_path)
        if not paper_text:
            raise ValueError("无法提取文本。请检查文件内容是否有效。")
        
        metadata = PaperMetadata(
            title=os.path.basename(file_path),
            authors=[],
            source="upload"
        )
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        
        engine = ConversationEngine(
            config=config,
            paper_cache=paper_cache,
            max_history_turns=0,
            prompt_overrides=prompt_overrides,
        )
        
        tasks[task_id]["progress"] = 30
        tasks[task_id]["stage"] = "PDF 提取完成"
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        
        # 2. Build analysis plan
        tasks[task_id]["progress"] = 40
        tasks[task_id]["stage"] = "构建分析计划..."
        
        tasks[task_id]["progress"] = 50
        tasks[task_id]["stage"] = "执行多维分析..."
        
        # Build questions from dimensions
        from new_architecture.analysis_dimensions import ANALYSIS_DIMENSIONS

        custom_dim_map: dict[str, dict] = {}
        if dimension_set_id is not None:
            try:
                from db.models import DimensionItem

                def _load_custom_dims():
                    import asyncio
                    from db import AsyncSessionLocal
                    from sqlalchemy import select as sa_select

                    async def _inner():
                        async with AsyncSessionLocal() as db:
                            items = (
                                await db.execute(
                                    sa_select(DimensionItem)
                                    .where(DimensionItem.set_id == dimension_set_id)
                                    .order_by(DimensionItem.sort_order)
                                )
                            ).scalars().all()
                            return {
                                it.dim_name: {
                                    "dim_key": it.dim_key,
                                    "prompt_content": it.prompt_content,
                                    "default_question": it.default_question,
                                    "is_builtin": bool(it.is_builtin),
                                }
                                for it in items
                            }
                    return asyncio.run(_inner())

                custom_dim_map = _load_custom_dims()
            except Exception:
                custom_dim_map = {}

        prev_items: dict[str, str] = {}
        if conflict_resolution == "incremental":
            try:
                prev_job_ids = asyncio.run(_query_prev_reading_jobs(user_id, bib_entry_id, "reading_long"))
                if prev_job_ids:
                    prev_ri = asyncio.run(_query_prev_reading_items(prev_job_ids[0]))
                    prev_items = {it.item_key: it.content for it in prev_ri if it.section_type in ("dimension", "custom")}
            except Exception:
                prev_items = {}

        results = {}
        total_dims = len(analysis_dims)

        dims_to_analyze = []
        for i, dim_key in enumerate(analysis_dims):
            item_key_for_dim = LONG_DIMENSION_KEYS.get(dim_key, f"long.{slugify_key_fragment(dim_key)}")
            if conflict_resolution == "incremental" and item_key_for_dim in prev_items:
                results[dim_key] = prev_items[item_key_for_dim]
                tasks[task_id]["logs"].append(f"⏭ {dim_key} 跳过（复用已有结果）")
                continue
            dims_to_analyze.append(dim_key)

        def _analyze_long_dim(dim_key):
            with deepseek_semaphore:
                if tasks[task_id]["status"] == "cancelled":
                    return dim_key, None, "cancelled"
                dim_map = {
                    "研究问题": "overview", "理论框架": "theory", "识别策略": "methodology",
                    "数据来源": "data_source", "变量度量": "variable_measurement",
                    "识别假设": "identification_assumptions", "统计结果": "results",
                    "机制分析": "mechanism", "稳健性检验": "robustness",
                    "外部有效性": "external_validity", "贡献与局限": "contributions_limitations",
                    "写作质量": "writing_quality",
                }
                mapped_key = dim_map.get(dim_key)
                try:
                    if mapped_key:
                        answer = engine.analyze_dimension(mapped_key)
                    elif custom_dim_map and dim_key in custom_dim_map:
                        answer = engine.analyze_dimension(dim_key, dim_meta=custom_dim_map[dim_key])
                    else:
                        answer = engine.analyze_dimension("overview")
                    return dim_key, answer, None
                except Exception as e:
                    return dim_key, f"[分析出错: {str(e)[:200]}]", str(e)

        workers = min(len(dims_to_analyze), 12)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_analyze_long_dim, dk): dk for dk in dims_to_analyze}
            done_count = 0
            for future in as_completed(futures):
                if tasks[task_id]["status"] == "cancelled":
                    break
                dim_key, answer, err = future.result()
                if err == "cancelled":
                    return
                results[dim_key] = answer
                done_count += 1
                tasks[task_id]["progress"] = 50 + int(40 * done_count / max(len(dims_to_analyze), 1))
                if err:
                    tasks[task_id]["logs"].append(f"⚠ {dim_key} 出错: {str(err)[:80]}")
                else:
                    tasks[task_id]["logs"].append(f"✓ {dim_key} 完成")
        
        # Handle custom question after all dimensions
        if custom_question and custom_question.strip():
            tasks[task_id]["stage"] = f"分析维度: 自定义问题..."
            tasks[task_id]["logs"].append(f"[自定义问题] {custom_question[:50]}...")
            try:
                answer = engine.analyze_dimension("custom", custom_question)
                results["自定义问题"] = answer
                tasks[task_id]["logs"].append(f"✓ 自定义问题 完成")
            except Exception as e:
                tasks[task_id]["logs"].append(f"⚠ 自定义问题 出错: {str(e)[:80]}")
                results["自定义问题"] = f"[分析出错: {str(e)[:200]}]"
        
        # Post-check: retry empty dimensions
        _LONG_DIM_MAP = {
            "研究问题": "overview", "理论框架": "theory", "识别策略": "methodology",
            "数据来源": "data_source", "变量度量": "variable_measurement",
            "识别假设": "identification_assumptions", "统计结果": "results",
            "机制分析": "mechanism", "稳健性检验": "robustness",
            "外部有效性": "external_validity", "贡献与局限": "contributions_limitations",
            "写作质量": "writing_quality",
        }
        def _retry_long(key):
            mapped = _LONG_DIM_MAP.get(key)
            if mapped:
                return engine.analyze_dimension(mapped)
            if custom_dim_map and key in custom_dim_map:
                return engine.analyze_dimension(key, dim_meta=custom_dim_map[key])
            if key == "自定义问题":
                return engine.analyze_dimension("custom", custom_question)
            return engine.analyze_dimension("overview")
        results = _check_and_retry_empty_dimensions(results, task_id, _retry_long)
        
        # 4. Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成报告..."
        
        original_name = get_original_filename(file_path)
        tasks[task_id]["stage"] = "后处理（元数据 + 参考文献）..."
        tasks[task_id]["logs"].append("开始并发后处理...")

        def _extract_meta_long():
            try:
                front_matter = extract_front_matter(file_path)
                metadata = extract_metadata_with_llm(front_matter, original_name, api_key=api_key)
                return metadata, None
            except Exception as exc:
                return None, str(exc)

        def _extract_refs_long():
            try:
                return _try_extract_references(
                    file_path, user_id, task_id, original_name, bib_entry_id, api_key=api_key,
                ), None
            except Exception as exc:
                return [], str(exc)

        metadata = None
        ref_artifacts = []
        with ThreadPoolExecutor(max_workers=2) as post_pool:
            meta_future = post_pool.submit(_extract_meta_long)
            ref_future = post_pool.submit(_extract_refs_long)
            metadata, meta_err = meta_future.result()
            ref_artifacts, ref_err = ref_future.result()

        if meta_err:
            tasks[task_id]["logs"].append(f"⚠ 元数据提取跳过: {meta_err}")
        elif metadata:
            tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        else:
            tasks[task_id]["logs"].append("⚠ 元数据提取未成功")
        if not metadata:
            from backend.services.pdf_metadata_llm import _empty_metadata
            metadata = _empty_metadata()

        if ref_artifacts is None:
            tasks[task_id]["logs"].append("✓ 参考文献已存在，跳过提取")
        elif ref_artifacts:
            tasks[task_id]["logs"].append(f"✓ 识别到 {len(ref_artifacts)} 个参考文献报告")
        else:
            tasks[task_id]["logs"].append("⚠ 参考文献自动提取未成功")

        safe_name = sanitize_filename(original_name)
        result_dir = get_results_dir(user_id, task_id)
        report_path = result_dir / f"{safe_name}_long_context.md"

        try:
            updated_fields = asyncio.run(_try_update_bib_metadata(bib_entry_id, file_path, original_name, api_key=api_key, metadata=metadata))
            if updated_fields:
                tasks[task_id]["logs"].append(f"✓ 文献库元数据已更新: {', '.join(updated_fields)}")
        except Exception as exc:
            tasks[task_id]["logs"].append(f"⚠ 文献库元数据更新跳过: {exc}")
        
        # Build frontmatter
        frontmatter = build_frontmatter(metadata, "长文本精读")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write(f"# 长文本精读报告\n\n")
            f.write(f"## 分析维度\n\n")
            f.write(f"<!--DIMENSIONS_START-->\n\n")
            for dim_key, answer in results.items():
                f.write(f"### {dim_key}\n\n")
                f.write(f"{answer}\n\n")
                f.write(f"<!--DIMENSION_BOUNDARY-->\n\n")
            f.write(f"<!--DIMENSIONS_END-->\n\n")
            f.write(f"---\n\n")
            f.write(f"*分析完成于 {tasks[task_id]['created_at'].strftime('%Y-%m-%d %H:%M')}*\n")
        
        # Summary
        preview_parts = []
        for dim_key, answer in results.items():
            preview_parts.append(f"## {dim_key}\n{answer[:500]}...")
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 全部完成！")
        tasks[task_id]["result"] = {
            "output_path": build_result_storage_path(report_path),
            "preview": "\n\n".join(preview_parts[:3]),
            "dimensions": list(results.keys()),
        }
        reading_items = build_long_reading_items(results, custom_question)
        # Note: ref_artifacts are already persisted by _try_extract_references via persist_trace_success
        # Only pass reading_final artifact to avoid duplicates
        all_artifacts = [{"artifact_type": "reading_final", "absolute_path": report_path}]
        asyncio.run(
            finalize_reading_success(
                task_id,
                bib_entry_id,
                user_id,
                all_artifacts,
                reading_items=reading_items,
            )
        )
        task_queue.mark_completed(task_id)
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)
        import asyncio

        task_queue.mark_completed(task_id)
        asyncio.run(finalize_reading_failure(task_id, bib_entry_id, str(e)))


def run_quant_task(
    task_id: str,
    user_id: int,
    bib_entry_id: str,
    file_path: str,
    prompt_overrides: dict[str, str],
    api_key: Optional[str] = None,
):
    """Run 7-step quantitative analysis. api_key is REQUIRED."""
    try:
        import asyncio

        logger.info("[quant:%s] 开始七步精读 user=%s bib=%s file=%s", task_id[:8], user_id, bib_entry_id, file_path)
        task_queue.mark_running(task_id)
        asyncio.run(sync_job_and_bib_start(task_id, bib_entry_id, stage="提取文本...", progress=10))
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取文本..."
        tasks[task_id]["logs"].append("[步骤 1/7] 提取文本...")
        
        api_key = validate_deepseek_key(api_key)
        logger.info("[quant:%s] API Key 验证通过", task_id[:8])
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(api_key)
        
        logger.info("[quant:%s] 开始提取文本...", task_id[:8])
        paper_text = extract_paper_text(file_path)
        if not paper_text:
            raise ValueError("无法提取文本。请检查文件内容是否有效。")
        logger.info("[quant:%s] 文本提取完成, 长度=%d字符", task_id[:8], len(paper_text))
        
        metadata = PaperMetadata(title=os.path.basename(file_path), authors=[], source="upload")
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        engine = ConversationEngine(config=config, paper_cache=paper_cache, max_history_turns=0)
        
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        logger.info("[quant:%s] PDF 提取完成，开始七步分析", task_id[:8])
        
        steps = list(QUANT_PROMPT_KEYS.items())
        
        def _analyze_quant_step(step_name, prompt_key):
            with deepseek_semaphore:
                if tasks[task_id]["status"] == "cancelled":
                    return step_name, None, "cancelled"
                try:
                    prompt_content = normalize_reading_prompt(prompt_overrides.get(prompt_key, ""))
                    answer = engine.ask(prompt_content)
                    return step_name, answer, None
                except Exception as e:
                    return step_name, f"[分析出错: {str(e)[:200]}]", str(e)

        results = {}
        with ThreadPoolExecutor(max_workers=min(len(steps), 7)) as pool:
            futures = {pool.submit(_analyze_quant_step, sn, pk): sn for sn, pk in steps}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                step_name, answer, err = future.result()
                if err == "cancelled":
                    return
                results[step_name] = answer
                if err:
                    tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(err)[:80]}")
                    logger.warning("[quant:%s] %s 出错: %s", task_id[:8], step_name, err)
                else:
                    tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
                    logger.info("[quant:%s] %s 完成, 回答长度=%d", task_id[:8], step_name, len(answer or ""))
                tasks[task_id]["progress"] = 15 + int(75 * done_count / len(steps))
        
        # Post-check: retry empty steps
        def _retry_quant(step_name_inner):
            pk = QUANT_PROMPT_KEYS[step_name_inner]
            return engine.ask(normalize_reading_prompt(prompt_overrides.get(pk, "")))
        results = _check_and_retry_empty_dimensions(results, task_id, _retry_quant)
        
        # Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成七步精读报告..."
        logger.info("[quant:%s] 七步分析完成，生成报告...", task_id[:8])
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        result_dir = get_results_dir(user_id, task_id)
        report_path = result_dir / f"{safe_name}_7step.md"
        
        tasks[task_id]["stage"] = "后处理（元数据 + 参考文献）..."
        tasks[task_id]["logs"].append("开始并发后处理...")

        def _extract_meta_quant():
            try:
                front_matter = extract_front_matter(file_path)
                metadata = extract_metadata_with_llm(front_matter, original_name, api_key=api_key)
                return metadata, None
            except Exception as exc:
                return None, str(exc)

        def _extract_refs_quant():
            try:
                return _try_extract_references(
                    file_path, user_id, task_id, original_name, bib_entry_id, api_key=api_key,
                ), None
            except Exception as exc:
                return [], str(exc)

        metadata = None
        ref_artifacts = []
        with ThreadPoolExecutor(max_workers=2) as post_pool:
            meta_future = post_pool.submit(_extract_meta_quant)
            ref_future = post_pool.submit(_extract_refs_quant)
            metadata, meta_err = meta_future.result()
            ref_artifacts, ref_err = ref_future.result()

        if meta_err:
            tasks[task_id]["logs"].append(f"⚠ 元数据提取跳过: {meta_err}")
        elif metadata:
            tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        else:
            tasks[task_id]["logs"].append("⚠ 元数据提取未成功")
        if not metadata:
            from backend.services.pdf_metadata_llm import _empty_metadata
            metadata = _empty_metadata()

        if ref_artifacts is None:
            tasks[task_id]["logs"].append("✓ 参考文献已存在，跳过提取")
        elif ref_artifacts:
            tasks[task_id]["logs"].append(f"✓ 识别到 {len(ref_artifacts)} 个参考文献报告")
        else:
            tasks[task_id]["logs"].append("⚠ 参考文献自动提取未成功")

        try:
            updated_fields = asyncio.run(_try_update_bib_metadata(bib_entry_id, file_path, original_name, api_key=api_key, metadata=metadata))
            if updated_fields:
                tasks[task_id]["logs"].append(f"✓ 文献库元数据已更新: {', '.join(updated_fields)}")
        except Exception as exc:
            tasks[task_id]["logs"].append(f"⚠ 文献库元数据更新跳过: {exc}")
        
        frontmatter = build_frontmatter(metadata, "七步精读")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write("# 七步精读报告\n\n")
            for step_name, answer in results.items():
                f.write(f"## {step_name}\n\n{answer}\n\n---\n\n")
        
        logger.info("[quant:%s] 报告已写入: %s", task_id[:8], report_path)
        
        preview = "\n\n".join([f"## {k}\n{v[:400]}..." for k, v in list(results.items())[:3]])
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 七步精读全部完成！")
        logger.info("[quant:%s] 七步精读全部完成", task_id[:8])
        tasks[task_id]["result"] = {
            "output_path": build_result_storage_path(report_path),
            "preview": preview,
            "steps": list(results.keys()),
        }
        reading_items = build_step_reading_items(results, mode="quant")
        # Note: ref_artifacts are already persisted by _try_extract_references via persist_trace_success
        # Only pass reading_final artifact to avoid duplicates
        all_artifacts = [{"artifact_type": "reading_final", "absolute_path": report_path}]
        asyncio.run(
            finalize_reading_success(
                task_id,
                bib_entry_id,
                user_id,
                all_artifacts,
                reading_items=reading_items,
            )
        )
        task_queue.mark_completed(task_id)
        
    except Exception as e:
        logger.error("[quant:%s] 七步精读失败: %s\n%s", task_id[:8], e, traceback.format_exc())
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)
        import asyncio

        task_queue.mark_completed(task_id)
        asyncio.run(finalize_reading_failure(task_id, bib_entry_id, str(e)))


def run_qual_task(
    task_id: str,
    user_id: int,
    bib_entry_id: str,
    file_path: str,
    prompt_overrides: dict[str, str],
    api_key: Optional[str] = None,
):
    """Run 4-step qualitative analysis. api_key is REQUIRED."""
    try:
        import asyncio

        logger.info("[qual:%s] 开始四步精读 user=%s bib=%s file=%s", task_id[:8], user_id, bib_entry_id, file_path)
        task_queue.mark_running(task_id)
        asyncio.run(sync_job_and_bib_start(task_id, bib_entry_id, stage="提取文本...", progress=10))
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取文本..."
        tasks[task_id]["logs"].append("[步骤 1/4] 提取文本...")
        
        api_key = validate_deepseek_key(api_key)
        logger.info("[qual:%s] API Key 验证通过", task_id[:8])
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(api_key)
        
        logger.info("[qual:%s] 开始提取文本...", task_id[:8])
        paper_text = extract_paper_text(file_path)
        if not paper_text:
            raise ValueError("无法提取文本。请检查文件内容是否有效。")
        logger.info("[qual:%s] 文本提取完成, 长度=%d字符", task_id[:8], len(paper_text))
        
        metadata = PaperMetadata(title=os.path.basename(file_path), authors=[], source="upload")
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        engine = ConversationEngine(config=config, paper_cache=paper_cache, max_history_turns=0)
        
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        logger.info("[qual:%s] PDF 提取完成，开始四步分析", task_id[:8])
        
        steps = list(QUAL_PROMPT_KEYS.items())
        
        def _analyze_qual_step(step_name, prompt_key):
            with deepseek_semaphore:
                if tasks[task_id]["status"] == "cancelled":
                    return step_name, None, "cancelled"
                try:
                    prompt_content = normalize_reading_prompt(prompt_overrides.get(prompt_key, ""))
                    answer = engine.ask(prompt_content)
                    return step_name, answer, None
                except Exception as e:
                    return step_name, f"[分析出错: {str(e)[:200]}]", str(e)

        results = {}
        with ThreadPoolExecutor(max_workers=min(len(steps), 4)) as pool:
            futures = {pool.submit(_analyze_qual_step, sn, pk): sn for sn, pk in steps}
            done_count = 0
            for future in as_completed(futures):
                done_count += 1
                step_name, answer, err = future.result()
                if err == "cancelled":
                    return
                results[step_name] = answer
                if err:
                    tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(err)[:80]}")
                    logger.warning("[qual:%s] %s 出错: %s", task_id[:8], step_name, err)
                else:
                    tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
                    logger.info("[qual:%s] %s 完成, 回答长度=%d", task_id[:8], step_name, len(answer or ""))
                tasks[task_id]["progress"] = 20 + int(70 * done_count / len(steps))
        
        # Post-check: retry empty steps
        def _retry_qual(step_name_inner):
            pk = QUAL_PROMPT_KEYS[step_name_inner]
            return engine.ask(normalize_reading_prompt(prompt_overrides.get(pk, "")))
        results = _check_and_retry_empty_dimensions(results, task_id, _retry_qual)
        
        # Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成四步精读报告..."
        logger.info("[qual:%s] 四步分析完成，生成报告...", task_id[:8])
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        result_dir = get_results_dir(user_id, task_id)
        report_path = result_dir / f"{safe_name}_4step.md"
        
        tasks[task_id]["stage"] = "后处理（元数据 + 参考文献）..."
        tasks[task_id]["logs"].append("开始并发后处理...")

        def _extract_meta_qual():
            try:
                front_matter = extract_front_matter(file_path)
                metadata = extract_metadata_with_llm(front_matter, original_name, api_key=api_key)
                return metadata, None
            except Exception as exc:
                return None, str(exc)

        def _extract_refs_qual():
            try:
                return _try_extract_references(
                    file_path, user_id, task_id, original_name, bib_entry_id, api_key=api_key,
                ), None
            except Exception as exc:
                return [], str(exc)

        metadata = None
        ref_artifacts = []
        with ThreadPoolExecutor(max_workers=2) as post_pool:
            meta_future = post_pool.submit(_extract_meta_qual)
            ref_future = post_pool.submit(_extract_refs_qual)
            metadata, meta_err = meta_future.result()
            ref_artifacts, ref_err = ref_future.result()

        if meta_err:
            tasks[task_id]["logs"].append(f"⚠ 元数据提取跳过: {meta_err}")
        elif metadata:
            tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        else:
            tasks[task_id]["logs"].append("⚠ 元数据提取未成功")
        if not metadata:
            from backend.services.pdf_metadata_llm import _empty_metadata
            metadata = _empty_metadata()

        if ref_artifacts is None:
            tasks[task_id]["logs"].append("✓ 参考文献已存在，跳过提取")
        elif ref_artifacts:
            tasks[task_id]["logs"].append(f"✓ 识别到 {len(ref_artifacts)} 个参考文献报告")
        else:
            tasks[task_id]["logs"].append("⚠ 参考文献自动提取未成功")

        try:
            updated_fields = asyncio.run(_try_update_bib_metadata(bib_entry_id, file_path, original_name, api_key=api_key, metadata=metadata))
            if updated_fields:
                tasks[task_id]["logs"].append(f"✓ 文献库元数据已更新: {', '.join(updated_fields)}")
        except Exception as exc:
            tasks[task_id]["logs"].append(f"⚠ 文献库元数据更新跳过: {exc}")
        
        frontmatter = build_frontmatter(metadata, "四步精读")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write("# 四步精读报告\n\n")
            for step_name, answer in results.items():
                f.write(f"## {step_name}\n\n{answer}\n\n---\n\n")
        
        logger.info("[qual:%s] 报告已写入: %s", task_id[:8], report_path)
        
        preview = "\n\n".join([f"## {k}\n{v[:400]}..." for k, v in list(results.items())[:2]])
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 四步精读全部完成！")
        logger.info("[qual:%s] 四步精读全部完成", task_id[:8])
        tasks[task_id]["result"] = {
            "output_path": build_result_storage_path(report_path),
            "preview": preview,
            "steps": list(results.keys()),
        }
        reading_items = build_step_reading_items(results, mode="qual")
        # Note: ref_artifacts are already persisted by _try_extract_references via persist_trace_success
        # Only pass reading_final artifact to avoid duplicates
        all_artifacts = [{"artifact_type": "reading_final", "absolute_path": report_path}]
        asyncio.run(
            finalize_reading_success(
                task_id,
                bib_entry_id,
                user_id,
                all_artifacts,
                reading_items=reading_items,
            )
        )
        task_queue.mark_completed(task_id)
        
    except Exception as e:
        logger.error("[qual:%s] 四步精读失败: %s\n%s", task_id[:8], e, traceback.format_exc())
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)
        import asyncio

        task_queue.mark_completed(task_id)
        asyncio.run(finalize_reading_failure(task_id, bib_entry_id, str(e)))


@router.post("/long/start")
async def start_long_context(
    request: LongContextRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start long context analysis"""
    file_record = await get_file_record(db, user, request.file_id)
    ensure_readable_file_type(file_record)
    file_path = get_file_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    bib_entry = await get_or_create_bib_entry(db, user, file_record)
    resolution = resolve_conflict_mode(request.force_overwrite, request.conflict_resolution)
    if resolution == "overwrite":
        await cleanup_old_reading_data(db, bib_entry, "reading_long")
    elif resolution == "check":
        existing = (
            await db.execute(
                select(Job).join(JobBibEntry, JobBibEntry.job_id == Job.id).where(
                    JobBibEntry.bib_entry_id == bib_entry.id,
                    Job.job_type == "reading_long",
                    Job.status == "success",
                ).limit(1)
            )
        ).scalars().first()
        if existing:
            raise HTTPException(status_code=409, detail={"detail": "already_read", "mode": "long"})
    prompt_overrides = await get_effective_prompt_map(db, user_id=user.id, prompt_type="long")
    task_id = await create_reading_job(
        db,
        user,
        file_record,
        bib_entry,
        "reading_long",
        {
            "analysis_dims": request.analysis_dims,
            "custom_question": request.custom_question,
            "extraction_method": request.extraction_method,
        },
    )
    await db.commit()
    tasks[task_id] = init_task_payload(task_id, "long_context", user.id, request.file_id, bib_entry.id)
    task_queue.enqueue(task_id, user.id, "long")
    
    thread = threading.Thread(
        target=run_long_context_task,
        args=(
            task_id,
            user.id,
            bib_entry.id,
            file_path,
            request.analysis_dims,
            request.custom_question,
            request.extraction_method,
            prompt_overrides,
            request.api_key,
            request.dimension_set_id,
            resolution,
        ),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.post("/quant/start")
async def start_quant(
    request: SimpleReadingRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start quantitative (7-step) analysis"""
    file_record = await get_file_record(db, user, request.file_id)
    ensure_readable_file_type(file_record)
    file_path = get_file_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    bib_entry = await get_or_create_bib_entry(db, user, file_record)
    resolution = resolve_conflict_mode(request.force_overwrite, request.conflict_resolution)
    if resolution == "overwrite":
        await cleanup_old_reading_data(db, bib_entry, "reading_quant")
    elif resolution == "check":
        existing = (
            await db.execute(
                select(Job).join(JobBibEntry, JobBibEntry.job_id == Job.id).where(
                    JobBibEntry.bib_entry_id == bib_entry.id,
                    Job.job_type == "reading_quant",
                    Job.status == "success",
                ).limit(1)
            )
        ).scalars().first()
        if existing:
            raise HTTPException(status_code=409, detail={"detail": "already_read", "mode": "quant"})
    prompt_overrides = await get_effective_prompt_map(db, user_id=user.id, prompt_type="quant")
    task_id = await create_reading_job(
        db,
        user,
        file_record,
        bib_entry,
        "reading_quant",
        {},
    )
    await db.commit()
    tasks[task_id] = init_task_payload(task_id, "quant", user.id, request.file_id, bib_entry.id)
    task_queue.enqueue(task_id, user.id, "quant")
    
    thread = threading.Thread(
        target=run_quant_task,
        args=(task_id, user.id, bib_entry.id, file_path, prompt_overrides, request.api_key),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.post("/qual/start")
async def start_qual(
    request: SimpleReadingRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start qualitative (4-step) analysis"""
    file_record = await get_file_record(db, user, request.file_id)
    ensure_readable_file_type(file_record)
    file_path = get_file_path(request.file_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    bib_entry = await get_or_create_bib_entry(db, user, file_record)
    resolution = resolve_conflict_mode(request.force_overwrite, request.conflict_resolution)
    if resolution == "overwrite":
        await cleanup_old_reading_data(db, bib_entry, "reading_qual")
    elif resolution == "check":
        existing = (
            await db.execute(
                select(Job).join(JobBibEntry, JobBibEntry.job_id == Job.id).where(
                    JobBibEntry.bib_entry_id == bib_entry.id,
                    Job.job_type == "reading_qual",
                    Job.status == "success",
                ).limit(1)
            )
        ).scalars().first()
        if existing:
            raise HTTPException(status_code=409, detail={"detail": "already_read", "mode": "qual"})
    prompt_overrides = await get_effective_prompt_map(db, user_id=user.id, prompt_type="qual")
    task_id = await create_reading_job(
        db,
        user,
        file_record,
        bib_entry,
        "reading_qual",
        {},
    )
    await db.commit()
    tasks[task_id] = init_task_payload(task_id, "qual", user.id, request.file_id, bib_entry.id)
    task_queue.enqueue(task_id, user.id, "qual")
    
    thread = threading.Thread(
        target=run_qual_task,
        args=(task_id, user.id, bib_entry.id, file_path, prompt_overrides, request.api_key),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.post("/batch/check-conflict")
async def batch_check_conflict(
    request: BatchCheckConflictRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="file_ids 不能为空。")
    if len(request.file_ids) > 50:
        raise HTTPException(status_code=400, detail="单次最多检查 50 个文件。")

    job_type_map = {"long": "reading_long", "quant": "reading_quant", "qual": "reading_qual"}
    job_type = job_type_map.get(request.mode)
    if not job_type:
        raise HTTPException(status_code=400, detail="mode 必须是 long/quant/qual")

    conflicts = []
    for file_id in request.file_ids:
        try:
            file_record = await get_file_record(db, user, file_id)
            ensure_readable_file_type(file_record)
            bib_entry = await get_or_create_bib_entry(db, user, file_record)

            existing_jobs = (
                await db.execute(
                    select(Job)
                    .join(JobBibEntry, JobBibEntry.job_id == Job.id)
                    .where(
                        JobBibEntry.bib_entry_id == bib_entry.id,
                        Job.job_type == job_type,
                        Job.status == "success",
                    )
                    .order_by(Job.created_at.desc())
                )
            ).scalars().all()

            if not existing_jobs:
                conflicts.append({"file_id": file_id, "file_name": file_record.original_name, "has_conflict": False})
                continue

            latest = existing_jobs[0]
            dimensions: list[str] = []
            incremental_dims: list[str] = []

            if request.analysis_dims and job_type == "reading_long":
                existing_items = (
                    await db.execute(
                        select(ReadingItem)
                        .where(
                            ReadingItem.job_id == latest.id,
                            ReadingItem.section_type.in_(["dimension", "custom"]),
                        )
                        .order_by(ReadingItem.sort_order)
                    )
                ).scalars().all()
                dimensions = [it.item_label for it in existing_items]
                existing_keys = {it.item_key for it in existing_items}
                incremental_dims = [
                    d for d in request.analysis_dims
                    if LONG_DIMENSION_KEYS.get(d, f"long.{slugify_key_fragment(d)}") not in existing_keys
                    and d not in dimensions
                ]

            conflicts.append({
                "file_id": file_id,
                "file_name": file_record.original_name,
                "has_conflict": True,
                "bib_entry": {
                    "id": bib_entry.id,
                    "title": bib_entry.title,
                    "reading_status": bib_entry.reading_status,
                },
                "existing_job": {
                    "job_id": latest.id,
                    "job_type": latest.job_type,
                    "created_at": latest.created_at.isoformat() if latest.created_at else None,
                    "dimensions": dimensions,
                    "mode_label": {
                        "reading_long": "长文本精读",
                        "reading_quant": "七步精读",
                        "reading_qual": "四步精读",
                    }.get(latest.job_type, latest.job_type),
                },
                "incremental_dims": incremental_dims,
            })
        except Exception:
            conflicts.append({"file_id": file_id, "file_name": file_id, "has_conflict": False})

    conflict_count = sum(1 for c in conflicts if c.get("has_conflict"))
    return {"conflicts": conflicts, "total": len(conflicts), "conflict_count": conflict_count}


@router.post("/batch/start")
async def start_batch_reading(
    request: BatchReadingRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="file_ids 不能为空。")
    if request.mode not in ("long", "quant", "qual"):
        raise HTTPException(status_code=400, detail="mode 必须是 long/quant/qual 之一。")
    if len(request.file_ids) > 50:
        raise HTTPException(status_code=400, detail="单次批量最多 50 个文件。")

    batch_id = str(uuid.uuid4())
    job_type_map = {"long": "reading_long", "quant": "reading_quant", "qual": "reading_qual"}
    job_type = job_type_map[request.mode]
    prompt_type_map = {"long": "long", "quant": "quant", "qual": "qual"}
    prompt_type = prompt_type_map[request.mode]

    prompt_overrides = await get_effective_prompt_map(db, user_id=user.id, prompt_type=prompt_type)

    batch_tasks = []
    for file_id in request.file_ids:
        try:
            file_record = await get_file_record(db, user, file_id)
            ensure_readable_file_type(file_record)
            file_path = get_file_path(file_id)
            if not file_path:
                batch_tasks.append({"file_id": file_id, "file_name": file_record.original_name, "task_id": None, "status": "skipped", "error": "文件路径未找到"})
                continue
            bib_entry = await get_or_create_bib_entry(db, user, file_record)
            batch_resolution = resolve_conflict_mode(request.force_overwrite, request.conflict_resolution, default="check")
            existing_job = await find_existing_reading_job(db, bib_entry.id, job_type)
            if batch_resolution == "overwrite" and existing_job is not None:
                await cleanup_old_reading_data(db, bib_entry, job_type)
            elif batch_resolution in ("check", "skip") and existing_job is not None:
                batch_tasks.append({"file_id": file_id, "file_name": file_record.original_name, "task_id": None, "status": "skipped", "error": "已有同模式精读结果"})
                continue

            params: dict = {}
            if request.mode == "long":
                params = {
                    "analysis_dims": request.analysis_dims or [],
                    "custom_question": request.custom_question,
                    "extraction_method": request.extraction_method,
                }

            task_id = await create_reading_job(db, user, file_record, bib_entry, job_type, params)
            await db.flush()
            job_obj = (await db.execute(select(Job).where(Job.id == task_id))).scalar_one()
            job_obj.batch_id = batch_id

            await db.commit()

            tasks[task_id] = init_task_payload(task_id, request.mode, user.id, file_id, bib_entry.id)
            task_queue.enqueue(task_id, user.id, request.mode)

            if request.mode == "long":
                thread = threading.Thread(
                    target=run_long_context_task,
                    args=(task_id, user.id, bib_entry.id, file_path, request.analysis_dims or [], request.custom_question, request.extraction_method, prompt_overrides, request.api_key, request.dimension_set_id, batch_resolution),
                    daemon=True,
                )
            elif request.mode == "quant":
                thread = threading.Thread(
                    target=run_quant_task,
                    args=(task_id, user.id, bib_entry.id, file_path, prompt_overrides, request.api_key),
                    daemon=True,
                )
            else:
                thread = threading.Thread(
                    target=run_qual_task,
                    args=(task_id, user.id, bib_entry.id, file_path, prompt_overrides, request.api_key),
                    daemon=True,
                )
            thread.start()

            batch_tasks.append({"file_id": file_id, "file_name": file_record.original_name, "task_id": task_id, "status": "queued"})
        except Exception as exc:
            batch_tasks.append({"file_id": file_id, "file_name": file_id, "task_id": None, "status": "error", "error": str(exc)[:200]})

    return {"batch_id": batch_id, "tasks": batch_tasks, "skipped_count": sum(1 for t in batch_tasks if t.get("status") == "skipped")}


@router.get("/batch/{batch_id}/status")
async def get_batch_status(
    batch_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    jobs = (
        await db.execute(
            select(Job).where(Job.batch_id == batch_id, Job.owner_user_id == user.id)
        )
    ).scalars().all()

    if not jobs:
        raise HTTPException(status_code=404, detail="Batch not found")

    task_summaries = []
    completed = 0
    failed = 0
    running = 0
    queued = 0

    for job in jobs:
        status_str = job.status
        if status_str == "success":
            completed += 1
        elif status_str in ("failed", "canceled"):
            failed += 1
        elif status_str == "running":
            running += 1
        else:
            queued += 1

        file_name = ""
        if job.input_file_id:
            file_rec = (await db.execute(select(File).where(File.id == job.input_file_id))).scalar_one_or_none()
            file_name = file_rec.original_name if file_rec else ""

        in_memory = tasks.get(job.id, {})
        progress = in_memory.get("progress", job.progress or 0)
        stage = in_memory.get("stage", job.current_stage or "")
        download_url = ""
        if status_str == "success":
            artifact = (
                await db.execute(
                    select(Artifact).where(Artifact.job_id == job.id, Artifact.artifact_type == "reading_final").limit(1)
                )
            ).scalar_one_or_none()
            if artifact:
                download_url = artifact.storage_path

        task_summaries.append({
            "task_id": job.id,
            "file_name": file_name,
            "status": status_str if status_str != "success" else "completed",
            "progress": progress,
            "stage": stage,
            "download_url": download_url,
        })

    return {
        "batch_id": batch_id,
        "total": len(jobs),
        "completed": completed,
        "failed": failed,
        "running": running,
        "queued": queued,
        "tasks": task_summaries,
    }


@router.get("/task/{task_id}/status")
async def get_task_status(
    task_id: str,
    user: User = Depends(current_user),
):
    queue_info = task_queue.get_task_queue_info(task_id)
    if queue_info and queue_info.get("status") == "queued":
        return {
            "status": "queued",
            "progress": 0,
            "stage": (
                f"排队中 (第 {queue_info['queue_position']} 位，"
                f"预计等待 {queue_info['estimated_wait_minutes']} 分钟)"
            ),
            "logs": [
                "任务已加入队列",
                f"排队位置: 第 {queue_info['queue_position']} 位",
                f"预计等待: {queue_info['estimated_wait_minutes']} 分钟",
            ],
            "queue_position": queue_info["queue_position"],
            "estimated_wait_seconds": queue_info["estimated_wait_seconds"],
            "estimated_wait_minutes": queue_info["estimated_wait_minutes"],
        }

    if task_id in tasks and tasks[task_id].get("owner_user_id") == user.id:
        return tasks[task_id]
    payload = await build_task_status_from_db(task_id, user.id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return payload


@router.post("/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    job = (
        await db.execute(select(Job).where(Job.id == task_id, Job.owner_user_id == user.id))
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task_id in tasks:
        tasks[task_id]["status"] = "cancelled"
        tasks[task_id]["stage"] = "已取消"
    task_queue.mark_completed(task_id)
    target_link = (
        await db.execute(
            select(JobBibEntry).where(JobBibEntry.job_id == task_id, JobBibEntry.role == "target")
        )
    ).scalar_one_or_none()
    await finalize_reading_failure(
        task_id,
        target_link.bib_entry_id if target_link is not None else "",
        "任务已取消",
        canceled=True,
    )
    return {"success": True}
