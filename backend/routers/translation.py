import logging
import os
import sys
import uuid
import threading
import json
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
load_dotenv(env_path)

from backend.utils.api_key import validate_deepseek_key

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import AsyncSessionLocal, get_db
from db.models import Artifact, BibEntry, File, Job, JobBibEntry, User
from result_storage import build_result_storage_path, get_results_root
from upload_storage import file_record_exists, lookup_path_by_file_id
from services.queue_manager import task_queue
from routers.reading import get_or_create_bib_entry

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()

RESULTS_ROOT = get_results_root()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

_translation_cancel_flags: dict[str, bool] = {}


class TranslationStartRequest(BaseModel):
    file_id: str
    bib_entry_id: Optional[str] = None
    api_key: Optional[str] = None
    max_workers: int = 5


class TranslationBindUploadRequest(BaseModel):
    file_id: str


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


def extract_paper_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".md", ".markdown"}:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    from extractor import PDFExtractor
    return PDFExtractor().extract_content(file_path) or ""


def _run_translation_task(
    task_id: str,
    user_id: int,
    file_id: str,
    file_type: str,
    storage_path: str,
    api_key: str,
    max_workers: int,
) -> None:
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        logger.info("[translation:%s] 开始翻译任务 user=%s file=%s type=%s workers=%s", task_id[:8], user_id, file_id, file_type, max_workers)
        task_queue.mark_running(task_id)

        async def _update_job(**kwargs):
            async with AsyncSessionLocal() as db:
                job = await db.get(Job, task_id)
                if job is None:
                    return
                for k, v in kwargs.items():
                    setattr(job, k, v)
                await db.commit()

        loop.run_until_complete(_update_job(status="running", progress=5, current_stage="准备文件..."))

        file_path = str(upload_storage_resolve(storage_path))
        logger.info("[translation:%s] 解析文件路径: %s -> %s exists=%s", task_id[:8], storage_path, file_path, os.path.exists(file_path))

        if file_type == "pdf":
            loop.run_until_complete(_update_job(current_stage="extracting", progress=5))
            logger.info("[translation:%s] 开始 PDF 文本提取...", task_id[:8])
            md_text = extract_paper_text(file_path)
            logger.info("[translation:%s] PDF 提取完成, 文本长度=%d", task_id[:8], len(md_text or ""))
            if not md_text:
                raise ValueError("PDF 文本提取失败")
        else:
            md_text = None
            logger.info("[translation:%s] Markdown 文件，跳过提取", task_id[:8])

        loop.run_until_complete(_update_job(current_stage="generating_glossary", progress=10))
        logger.info("[translation:%s] 加载 translation_pipeline...", task_id[:8])

        from translation_pipeline import translate_md_file

        result_dir = get_results_dir(user_id, task_id)
        out_dir = str(result_dir)
        logger.info("[translation:%s] 输出目录: %s", task_id[:8], out_dir)

        def progress_cb(stage: str, current: int, total: int):
            logger.info("[translation:%s] 阶段=%s 进度=%d%%", task_id[:8], stage, current)
            try:
                loop.run_until_complete(_update_job(current_stage=stage, progress=current))
            except Exception as e:
                logger.warning("[translation:%s] 进度更新失败: %s", task_id[:8], e)

        def cancel_check():
            return _translation_cancel_flags.get(task_id, False)

        if md_text is not None:
            from pathlib import Path as P
            stem = P(file_path).stem
            for suf in ("_paddleocr", "_raw", "_segmented"):
                if stem.endswith(suf):
                    stem = stem[: -len(suf)]
                    break
            tmp_md = os.path.join(out_dir, f"{stem}_source.md")
            with open(tmp_md, "w", encoding="utf-8") as f:
                f.write(md_text)
            md_source_path = tmp_md
            logger.info("[translation:%s] PDF 提取文本写入临时文件: %s (%d字符)", task_id[:8], tmp_md, len(md_text))
        else:
            md_source_path = file_path

        logger.info("[translation:%s] 开始调用 translate_md_file...", task_id[:8])
        cn_path, glossary_path = translate_md_file(
            md_source_path,
            out_dir=out_dir,
            api_key=api_key,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
            max_workers=max_workers,
            pdf_fulltext=md_text,
        )
        logger.info("[translation:%s] 翻译完成 cn=%s glossary=%s", task_id[:8], cn_path, glossary_path)

        if cancel_check():
            loop.run_until_complete(_update_job(status="canceled", progress=0, current_stage="已取消", finished_at=utcnow_naive()))
            task_queue.mark_completed(task_id)
            return

        loop.run_until_complete(_update_job(current_stage="saving", progress=95))

        artifact_files = [
            {"artifact_type": "translation_md", "absolute_path": cn_path},
            {"artifact_type": "translation_glossary", "absolute_path": glossary_path},
        ]

        async def _finalize():
            async with AsyncSessionLocal() as db:
                job = await db.get(Job, task_id)
                owner = await db.get(User, user_id)
                if job is None or owner is None:
                    logger.warning("[translation:%s] _finalize: job=%s owner=%s", task_id[:8], job is not None, owner is not None)
                    return

                for sort_order, af in enumerate(artifact_files):
                    abs_path = Path(af["absolute_path"])
                    logger.info("[translation:%s] 保存产物: %s (%s) exists=%s size=%s", task_id[:8], abs_path.name, af["artifact_type"], abs_path.exists(), abs_path.stat().st_size if abs_path.exists() else "N/A")
                    art = Artifact(
                        job_id=task_id,
                        owner_user_id=user_id,
                        artifact_type=af["artifact_type"],
                        filename=abs_path.name,
                        storage_path=build_result_storage_path(abs_path),
                        size_bytes=abs_path.stat().st_size if abs_path.exists() else None,
                        sort_order=sort_order,
                        expires_at=compute_expires_at(owner),
                    )
                    db.add(art)

                job.status = "success"
                job.progress = 100
                job.current_stage = "完成"
                job.error_msg = None
                job.finished_at = utcnow_naive()
                await db.commit()

        loop.run_until_complete(_finalize())
        task_queue.mark_completed(task_id)
        logger.info("[translation:%s] 任务成功完成", task_id[:8])

    except Exception as e:
        logger.error("[translation:%s] 任务失败: %s\n%s", task_id[:8], e, traceback.format_exc())
        try:
            loop.run_until_complete(_update_job(
                status="failed",
                current_stage=f"错误: {str(e)[:200]}",
                error_msg=str(e),
                finished_at=utcnow_naive(),
            ))
        except Exception as e2:
            logger.error("[translation:%s] 更新失败状态也失败: %s", task_id[:8], e2)
        task_queue.mark_completed(task_id)
    finally:
        _translation_cancel_flags.pop(task_id, None)
        loop.close()


def upload_storage_resolve(storage_path: str) -> Path:
    from upload_storage import resolve_storage_path
    return resolve_storage_path(storage_path)


async def clear_stale_bib_file_links(db: AsyncSession, *, user_id: int, file_id: str) -> int:
    rows = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == user_id,
                or_(BibEntry.source_file_id == file_id, BibEntry.markdown_source_file_id == file_id),
            )
        )
    ).scalars().all()
    repaired = 0
    for entry in rows:
        changed = False
        if entry.source_file_id == file_id:
            entry.source_file_id = None
            changed = True
        if entry.markdown_source_file_id == file_id:
            entry.markdown_source_file_id = None
            changed = True
        if changed:
            entry.updated_at = utcnow_naive()
            repaired += 1
    return repaired


@router.get("/translatable")
async def list_translatable(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(BibEntry, File)
        .join(File, File.id == BibEntry.source_file_id)
        .where(
            BibEntry.owner_user_id == user.id,
            BibEntry.source_file_id.isnot(None),
            BibEntry.language == "en",
            File.file_type.in_(["pdf", "markdown"]),
        )
        .order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()

    translated_entry_ids: set[str] = set()
    entry_artifacts: dict[str, list[dict]] = {}
    if rows:
        entry_ids = [entry.id for entry, _ in rows]
        trans_rows = (
            await db.execute(
                select(JobBibEntry.bib_entry_id)
                .join(Artifact, Artifact.job_id == JobBibEntry.job_id)
                .where(
                    JobBibEntry.bib_entry_id.in_(entry_ids),
                    Artifact.artifact_type == "translation_md",
                )
                .group_by(JobBibEntry.bib_entry_id)
            )
        ).scalars().all()
        translated_entry_ids = set(trans_rows)

        if translated_entry_ids:
            all_jbe = (
                await db.execute(
                    select(JobBibEntry, Artifact)
                    .join(Artifact, Artifact.job_id == JobBibEntry.job_id)
                    .where(
                        JobBibEntry.bib_entry_id.in_(translated_entry_ids),
                    )
                    .order_by(Artifact.sort_order, Artifact.id)
                )
            ).all()
            for jbe, art in all_jbe:
                entry_artifacts.setdefault(jbe.bib_entry_id, []).append({
                    "id": art.id,
                    "artifact_type": art.artifact_type,
                    "filename": art.filename,
                    "storage_path": art.storage_path,
                    "size_bytes": art.size_bytes,
                })

    results = []
    repaired = 0
    for entry, source_file in rows:
        if not file_record_exists(source_file):
            repaired += await clear_stale_bib_file_links(db, user_id=user.id, file_id=source_file.id)
            continue
        results.append({
            "bib_entry_id": entry.id,
            "title": entry.title,
            "authors": json.loads(entry.authors_json) if entry.authors_json else [],
            "year": entry.year,
            "journal": entry.journal,
            "file_id": source_file.id,
            "file_name": source_file.original_name,
            "file_type": source_file.file_type,
            "has_translation": entry.id in translated_entry_ids,
            "artifacts": entry_artifacts.get(entry.id, []),
        })
    if repaired:
        await db.commit()
    return {"entries": results}


@router.post("/bind-upload")
async def bind_translation_upload(
    request: TranslationBindUploadRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = (
        await db.execute(
            select(File).where(File.id == request.file_id, File.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if file_record is None or file_record.file_type not in ("pdf", "markdown"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Translation source file not found",
        )

    bib_entry = await get_or_create_bib_entry(db, user, file_record)
    if not bib_entry.language:
        bib_entry.language = "en"
    await db.commit()

    return {
        "bib_entry_id": bib_entry.id,
        "title": bib_entry.title,
        "language": bib_entry.language,
        "file_id": file_record.id,
        "file_name": file_record.original_name,
        "file_type": file_record.file_type,
    }


@router.post("/start")
async def start_translation(
    request: TranslationStartRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = (
        await db.execute(
            select(File).where(File.id == request.file_id, File.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if file_record is None:
        logger.warning("[translation] File not found: file_id=%s user=%s", request.file_id, user.id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    if file_record.file_type not in ("pdf", "markdown"):
        logger.warning("[translation] Unsupported file_type=%s for file_id=%s", file_record.file_type, request.file_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="翻译仅支持 PDF 或 Markdown 文件。",
        )
    if not file_record_exists(file_record):
        repaired = await clear_stale_bib_file_links(db, user_id=user.id, file_id=file_record.id)
        if repaired:
            await db.commit()
        logger.warning("[translation] Missing source file: file_id=%s user=%s repaired=%s", file_record.id, user.id, repaired)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="源文件已丢失，请重新上传原文后再发起翻译。",
        )

    logger.info("[translation] 收到翻译请求: user=%s file=%s type=%s bib=%s", user.id, file_record.original_name, file_record.file_type, request.bib_entry_id)

    task_id = str(uuid.uuid4())
    job = Job(
        id=task_id,
        owner_user_id=user.id,
        job_type="translation",
        status="pending",
        input_file_id=file_record.id,
        params_json=json.dumps({"max_workers": request.max_workers, "bib_entry_id": request.bib_entry_id}, ensure_ascii=False),
        progress=0,
        current_stage="等待开始...",
        expires_at=compute_expires_at(user),
    )
    db.add(job)

    if request.bib_entry_id:
        bib = (
            await db.execute(
                select(BibEntry).where(BibEntry.id == request.bib_entry_id, BibEntry.owner_user_id == user.id)
            )
        ).scalar_one_or_none()
        if bib:
            db.add(JobBibEntry(
                job_id=task_id,
                bib_entry_id=bib.id,
                role="target",
                sort_order=0,
            ))

    await db.commit()

    api_key = request.api_key
    if api_key:
        try:
            api_key = validate_deepseek_key(api_key)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    task_queue.enqueue(task_id, user.id, "translation")

    storage_path = file_record.storage_path

    thread = threading.Thread(
        target=_run_translation_task,
        args=(task_id, user.id, file_record.id, file_record.file_type, storage_path, api_key or "", request.max_workers),
        daemon=True,
    )
    thread.start()

    return {"job_id": task_id, "status": "pending"}


@router.get("/artifacts/{bib_entry_id}")
async def get_translation_artifacts(
    bib_entry_id: str,
    user: User = Depends(current_user),
):
    async with AsyncSessionLocal() as db:
        job_row = (
            await db.execute(
                select(Job)
                .join(JobBibEntry, JobBibEntry.job_id == Job.id)
                .where(
                    JobBibEntry.bib_entry_id == bib_entry_id,
                    Job.owner_user_id == user.id,
                    Job.job_type == "translation",
                    Job.status == "success",
                )
                .order_by(Job.finished_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if job_row is None:
            return {"artifacts": []}
        artifacts = (
            await db.execute(
                select(Artifact)
                .where(Artifact.job_id == job_row.id)
                .order_by(Artifact.sort_order, Artifact.id)
            )
        ).scalars().all()
        return {
            "artifacts": [
                {
                    "id": art.id,
                    "artifact_type": art.artifact_type,
                    "filename": art.filename,
                    "storage_path": art.storage_path,
                    "size_bytes": art.size_bytes,
                }
                for art in artifacts
            ],
        }


@router.get("/{job_id}/status")
async def get_translation_status(
    job_id: str,
    user: User = Depends(current_user),
):
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(
                select(Job).where(Job.id == job_id, Job.owner_user_id == user.id)
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        queue_info = task_queue.get_task_queue_info(job_id)
        stage_text = job.current_stage or ""
        if queue_info and queue_info.get("status") == "queued":
            stage_text = (
                f"排队中 (第 {queue_info['queue_position']} 位，"
                f"预计等待 {queue_info['estimated_wait_minutes']} 分钟)"
            )

        return {
            "job_id": job.id,
            "status": job.status if job.status != "success" else "completed",
            "progress": job.progress or 0,
            "current_stage": stage_text,
            "error_msg": job.error_msg,
        }


@router.get("/{job_id}/result")
async def get_translation_result(
    job_id: str,
    user: User = Depends(current_user),
):
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(
                select(Job).where(Job.id == job_id, Job.owner_user_id == user.id)
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if job.status != "success":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job not completed yet")

        artifacts = (
            await db.execute(
                select(Artifact).where(Artifact.job_id == job_id).order_by(Artifact.sort_order, Artifact.id)
            )
        ).scalars().all()

        return {
            "job_id": job.id,
            "status": "completed",
            "artifacts": [
                {
                    "id": art.id,
                    "artifact_type": art.artifact_type,
                    "filename": art.filename,
                    "storage_path": art.storage_path,
                    "size_bytes": art.size_bytes,
                }
                for art in artifacts
            ],
        }


@router.post("/cancel/{job_id}")
async def cancel_translation(
    job_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    job = (
        await db.execute(
            select(Job).where(Job.id == job_id, Job.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.status in ("success", "failed", "canceled"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job already finished")

    _translation_cancel_flags[job_id] = True
    task_queue.mark_completed(job_id)

    job.status = "canceled"
    job.current_stage = "已取消"
    job.finished_at = utcnow_naive()
    await db.commit()

    return {"success": True}


@router.delete("/artifacts")
async def delete_translation_artifacts(
    artifact_ids: list[int],
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = 0
    for aid in artifact_ids:
        art = (
            await db.execute(
                select(Artifact).where(Artifact.id == aid, Artifact.owner_user_id == user.id)
            )
        ).scalar_one_or_none()
        if art is None:
            continue
        try:
            from result_storage import resolve_result_path
            fp = resolve_result_path(art.storage_path)
            if fp.exists() and fp.is_file():
                fp.unlink()
        except Exception:
            pass
        await db.delete(art)
        deleted += 1
    if deleted:
        await db.commit()
    return {"deleted": deleted}
