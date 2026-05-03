"""Reading Router - authenticated reading jobs with DB persistence."""
import logging
import os
import sys
import uuid
import threading
import re
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path)

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import AsyncSessionLocal, PROJECT_ROOT, get_db
from db.models import Artifact, BibEntry, File, Job, JobBibEntry, ReadingItem, User
from db.utils import compute_dedup_key, title_match_score
from backend.routers.metadata_extractor import extract_metadata, build_frontmatter
from prompt_service import get_effective_prompt_map
from upload_storage import lookup_original_name, lookup_path_by_file_id

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()

RESULTS_ROOT = PROJECT_ROOT / "deep_reading_results"
RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

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
    analysis_dims: list[str]  # e.g. ["研究问题", "理论框架", "识别策略"]
    custom_question: Optional[str] = None
    extraction_method: str = "full"  # full or preview
    api_key: Optional[str] = None


class SimpleReadingRequest(BaseModel):
    file_id: str
    api_key: Optional[str] = None


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


def build_result_storage_path(absolute_path: Path) -> str:
    try:
        return absolute_path.relative_to(RESULTS_ROOT).as_posix()
    except ValueError:
        return absolute_path.as_posix()


def infer_bib_source_db(file_record: File) -> str:
    return "md_extracted" if file_record.file_type == "markdown" else "pdf_extracted"


async def get_file_record(db: AsyncSession, user: User, file_id: str) -> File:
    record = (
        await db.execute(select(File).where(File.id == file_id, File.owner_user_id == user.id))
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return record


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
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
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
) -> list[dict]:
    """Try to extract references during reading. Returns artifact files on success, empty on failure."""
    try:
        from routers.references import write_trace_outputs, persist_trace_success
        from services.deepseek_refs import extract_references_deepseek, trace_citations_deepseek

        references = extract_references_deepseek(file_path, api_key=api_key)
        if not references:
            return []

        references = trace_citations_deepseek(file_path, references, api_key=api_key)

        for ref in references:
            ref["dedup_key"] = compute_dedup_key(
                ref.get("doi"), ref.get("title") or ref.get("raw_text", "")[:80],
                ref.get("authors", []), ref.get("year"),
            )
            ref.setdefault("citations", [])

        artifact_files = write_trace_outputs(user_id, task_id, source_title, references)

        # Create a separate reference_trace job for database persistence
        ref_task_id = str(uuid.uuid4())
        import asyncio
        asyncio.run(_create_ref_trace_job_and_persist(
            ref_task_id, user_id, bib_entry_id, references, artifact_files,
        ))

        return artifact_files
    except Exception as e:
        logging.getLogger(__name__).warning("Reference extraction during reading failed: %s", e)
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
):
    """Run long context analysis in background thread. api_key is REQUIRED."""
    try:
        import asyncio

        asyncio.run(sync_job_and_bib_start(task_id, bib_entry_id, stage="提取 PDF...", progress=10))
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取 PDF..."
        tasks[task_id]["logs"].append("[阶段 1/3] 提取 PDF...")
        
        # Validate API key first
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始精读。")
        
        final_api_key = api_key.strip()
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(final_api_key)
        
        # 3. Read PDF text and create cache
        tasks[task_id]["progress"] = 30
        tasks[task_id]["stage"] = "读取论文内容..."
        tasks[task_id]["logs"].append("[阶段 2/3] 读取论文内容...")
        
        # Extract PDF text using project extractor
        from extractor import PDFExtractor
        extractor = PDFExtractor()
        paper_text = extractor.extract_content(file_path)
        if not paper_text:
            raise ValueError("无法从 PDF 提取文本。请检查文件是否为扫描件或图片PDF。")
        
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
        
        results = {}
        total_dims = len(analysis_dims)
        for i, dim_key in enumerate(analysis_dims):
            if tasks[task_id]["status"] == "cancelled":
                return
            
            # Map Chinese dim name to key
            dim_map = {
                "研究问题": "overview",
                "理论框架": "theory",
                "识别策略": "methodology",
                "数据来源": "data_source",
                "变量度量": "variable_measurement",
                "识别假设": "identification_assumptions",
                "统计结果": "results",
                "机制分析": "mechanism",
                "稳健性检验": "robustness",
                "外部有效性": "external_validity",
                "贡献与局限": "contributions_limitations",
                "写作质量": "writing_quality",
            }
            mapped_key = dim_map.get(dim_key, "overview")
            
            tasks[task_id]["stage"] = f"分析维度 {i+1}/{total_dims}: {dim_key}..."
            tasks[task_id]["logs"].append(f"[{i+1}/{total_dims}] {dim_key}...")
            
            try:
                answer = engine.analyze_dimension(mapped_key)
                results[dim_key] = answer
                tasks[task_id]["logs"].append(f"✓ {dim_key} 完成")
            except Exception as e:
                tasks[task_id]["logs"].append(f"⚠ {dim_key} 出错: {str(e)[:80]}")
                results[dim_key] = f"[分析出错: {str(e)[:200]}]"
        
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
        
        # 4. Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成报告..."
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        result_dir = get_results_dir(user_id, task_id)
        report_path = result_dir / f"{safe_name}_long_context.md"
        
        # Extract metadata
        tasks[task_id]["stage"] = "提取论文元数据..."
        tasks[task_id]["logs"].append("提取论文元数据...")
        metadata = extract_metadata(paper_text, final_api_key)
        tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        
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
        
        # Extract references (optional, does not fail the main task)
        tasks[task_id]["stage"] = "提取参考文献..."
        tasks[task_id]["logs"].append("尝试提取参考文献...")
        original_name = get_original_filename(file_path)
        ref_artifacts = _try_extract_references(
            file_path, user_id, task_id, original_name, bib_entry_id, api_key=api_key,
        )
        if ref_artifacts:
            tasks[task_id]["logs"].append(f"✓ 识别到参考文献，已生成参考文献报告")
        
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
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)
        import asyncio

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

        asyncio.run(sync_job_and_bib_start(task_id, bib_entry_id, stage="提取 PDF...", progress=10))
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取 PDF..."
        tasks[task_id]["logs"].append("[步骤 1/7] 提取 PDF...")
        
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始精读。")
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(api_key.strip())
        
        # Extract PDF text using project extractor
        from extractor import PDFExtractor
        extractor = PDFExtractor()
        paper_text = extractor.extract_content(file_path)
        if not paper_text:
            raise ValueError("无法从 PDF 提取文本。请检查文件是否为扫描件或图片PDF。")
        
        metadata = PaperMetadata(title=os.path.basename(file_path), authors=[], source="upload")
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        engine = ConversationEngine(config=config, paper_cache=paper_cache, max_history_turns=0)
        
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        
        steps = list(QUANT_PROMPT_KEYS.items())
        
        results = {}
        for i, (step_name, prompt_key) in enumerate(steps):
            if tasks[task_id]["status"] == "cancelled":
                return
            
            tasks[task_id]["progress"] = 15 + i * 12
            tasks[task_id]["stage"] = step_name
            tasks[task_id]["logs"].append(f"[{i+1}/7] {step_name}...")
            
            try:
                prompt_content = normalize_reading_prompt(prompt_overrides.get(prompt_key, ""))
                answer = engine.ask(prompt_content)
                results[step_name] = answer
                tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
            except Exception as e:
                tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(e)[:80]}")
                results[step_name] = f"[分析出错: {str(e)[:200]}]"
        
        # Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成七步精读报告..."
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        result_dir = get_results_dir(user_id, task_id)
        report_path = result_dir / f"{safe_name}_7step.md"
        
        # Extract metadata
        tasks[task_id]["stage"] = "提取论文元数据..."
        tasks[task_id]["logs"].append("提取论文元数据...")
        metadata = extract_metadata(paper_text, api_key.strip())
        tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        
        # Build frontmatter
        frontmatter = build_frontmatter(metadata, "七步精读")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write("# 七步精读报告\n\n")
            for step_name, answer in results.items():
                f.write(f"## {step_name}\n\n{answer}\n\n---\n\n")
        
        preview = "\n\n".join([f"## {k}\n{v[:400]}..." for k, v in list(results.items())[:3]])
        
        # Extract references (optional, does not fail the main task)
        tasks[task_id]["stage"] = "提取参考文献..."
        tasks[task_id]["logs"].append("尝试提取参考文献...")
        original_name = get_original_filename(file_path)
        ref_artifacts = _try_extract_references(
            file_path, user_id, task_id, original_name, bib_entry_id, api_key=api_key,
        )
        if ref_artifacts:
            tasks[task_id]["logs"].append(f"✓ 识别到参考文献，已生成参考文献报告")
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 七步精读全部完成！")
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
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)
        import asyncio

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

        asyncio.run(sync_job_and_bib_start(task_id, bib_entry_id, stage="提取 PDF...", progress=10))
        tasks[task_id]["status"] = "running"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["stage"] = "提取 PDF..."
        tasks[task_id]["logs"].append("[步骤 1/4] 提取 PDF...")
        
        if not api_key or not api_key.strip():
            raise ValueError("未提供 API Key。请在前端输入 DeepSeek API Key 后再开始精读。")
        
        from new_architecture.conversation_engine import ConversationEngine
        from new_architecture.paper_cache import PaperCache, PaperMetadata
        from new_architecture.config import Config
        
        config = Config.from_key(api_key.strip())
        
        # Extract PDF text using project extractor
        from extractor import PDFExtractor
        extractor = PDFExtractor()
        paper_text = extractor.extract_content(file_path)
        if not paper_text:
            raise ValueError("无法从 PDF 提取文本。请检查文件是否为扫描件或图片PDF。")
        
        metadata = PaperMetadata(title=os.path.basename(file_path), authors=[], source="upload")
        paper_cache = PaperCache(text=paper_text, metadata=metadata)
        engine = ConversationEngine(config=config, paper_cache=paper_cache, max_history_turns=0)
        
        tasks[task_id]["logs"].append("✓ PDF 提取完成")
        
        steps = list(QUAL_PROMPT_KEYS.items())
        
        results = {}
        for i, (step_name, prompt_key) in enumerate(steps):
            if tasks[task_id]["status"] == "cancelled":
                return
            
            tasks[task_id]["progress"] = 20 + i * 20
            tasks[task_id]["stage"] = step_name
            tasks[task_id]["logs"].append(f"[{i+1}/4] {step_name}...")
            
            try:
                prompt_content = normalize_reading_prompt(prompt_overrides.get(prompt_key, ""))
                answer = engine.ask(prompt_content)
                results[step_name] = answer
                tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
            except Exception as e:
                tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(e)[:80]}")
                results[step_name] = f"[分析出错: {str(e)[:200]}]"
        
        # Generate report
        tasks[task_id]["progress"] = 95
        tasks[task_id]["stage"] = "生成四步精读报告..."
        
        original_name = get_original_filename(file_path)
        safe_name = sanitize_filename(original_name)
        result_dir = get_results_dir(user_id, task_id)
        report_path = result_dir / f"{safe_name}_4step.md"
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# 四步精读报告\n\n")
            for step_name, answer in results.items():
                f.write(f"## {step_name}\n\n{answer}\n\n---\n\n")
        
        preview = "\n\n".join([f"## {k}\n{v[:400]}..." for k, v in list(results.items())[:2]])
        
        # Extract references (optional, does not fail the main task)
        tasks[task_id]["stage"] = "提取参考文献..."
        tasks[task_id]["logs"].append("尝试提取参考文献...")
        original_name = get_original_filename(file_path)
        ref_artifacts = _try_extract_references(
            file_path, user_id, task_id, original_name, bib_entry_id, api_key=api_key,
        )
        if ref_artifacts:
            tasks[task_id]["logs"].append(f"✓ 识别到参考文献，已生成参考文献报告")
        
        tasks[task_id]["progress"] = 100
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["stage"] = "完成"
        tasks[task_id]["logs"].append("✅ 四步精读全部完成！")
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
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["stage"] = f"错误: {str(e)}"
        tasks[task_id]["logs"].append(f"❌ {str(e)}")
        tasks[task_id]["error"] = str(e)
        import asyncio

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
    
    thread = threading.Thread(
        target=run_qual_task,
        args=(task_id, user.id, bib_entry.id, file_path, prompt_overrides, request.api_key),
        daemon=True
    )
    thread.start()
    
    return {"task_id": task_id, "status": "queued"}


@router.get("/task/{task_id}/status")
async def get_task_status(
    task_id: str,
    user: User = Depends(current_user),
):
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
