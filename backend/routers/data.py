"""Data export/import router for user data portability (.dra format)."""
from __future__ import annotations

import os
import asyncio
import logging
import tempfile
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import AsyncSessionLocal, get_db
from db.models import User
from services.data_portability import export_user_data, import_user_data

router = APIRouter()
logger = logging.getLogger(__name__)

# Simple in-memory rate limiting
_export_counts: dict[int, list[datetime]] = {}
_import_counts: dict[int, list[datetime]] = {}

_MAX_EXPORTS_PER_DAY = 5
_MAX_IMPORTS_PER_DAY = 3
_MAX_IMPORT_SIZE = 1024 * 1024 * 1024
_IMPORT_CHUNK_SIZE_LIMIT = 10 * 1024 * 1024

_import_tasks: dict[str, dict[str, Any]] = {}
_user_active_imports: dict[int, str] = {}
_import_task_lock = threading.Lock()
_import_upload_lock = threading.Lock()
_import_upload_sessions: dict[str, dict[str, Any]] = {}


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _check_rate_limit(counts: dict[int, list[datetime]], user_id: int, max_count: int) -> bool:
    now = _utc_now()
    window_start = now - timedelta(hours=24)
    # Keep only entries within the last 24h
    counts[user_id] = [t for t in counts.get(user_id, []) if t >= window_start]
    return len(counts[user_id]) < max_count


def _record_rate_limit(counts: dict[int, list[datetime]], user_id: int) -> None:
    counts.setdefault(user_id, []).append(_utc_now())


def _check_active_import(user_id: int) -> None:
    with _import_task_lock:
        active_job_id = _user_active_imports.get(user_id)
        active_task = _import_tasks.get(active_job_id or "")
        if active_job_id and active_task and active_task.get("status") in {"pending", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="已有导入任务正在运行，请等待完成后再导入。",
            )


def _set_import_task(job_id: str, **updates: Any) -> None:
    with _import_task_lock:
        task = _import_tasks.get(job_id)
        if task is None:
            return
        task.update(updates)
        task["updated_at"] = _utc_now().isoformat()


def _run_import_task(job_id: str, user_id: int, tmp_path: Path) -> None:
    def progress(stage: str, value: int) -> None:
        _set_import_task(job_id, current_stage=stage, progress=max(0, min(100, value)))

    async def runner() -> None:
        progress("正在准备导入任务...", 1)
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user is None:
                raise ValueError("导入用户不存在或已被删除。")

            result = await import_user_data(db, user, tmp_path, progress_cb=progress)
            _record_rate_limit(_import_counts, user_id)
            _set_import_task(
                job_id,
                status="success",
                progress=100,
                current_stage="导入完成。",
                result={
                    "success": True,
                    "message": "导入成功。",
                    "cleared": result["cleared"],
                    "imported": result["imported"],
                    "files_restored": result["files_restored"],
                    "files_missing": result["files_missing"],
                },
                finished_at=_utc_now().isoformat(),
            )

    try:
        _set_import_task(job_id, status="running", current_stage="正在启动导入任务...", progress=1)
        asyncio.run(runner())
    except Exception as exc:
        logger.error("[data-import:%s] Import failed: %s", job_id, exc, exc_info=True)
        _set_import_task(
            job_id,
            status="failed",
            current_stage=f"导入失败：{exc}",
            error_msg=str(exc),
            finished_at=_utc_now().isoformat(),
        )
    finally:
        with _import_task_lock:
            if _user_active_imports.get(user_id) == job_id:
                _user_active_imports.pop(user_id, None)
        if tmp_path.exists():
            os.unlink(tmp_path)


@router.post("/export")
async def export_data(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Export all user data as a .dra zip package."""
    if not _check_rate_limit(_export_counts, user.id, _MAX_EXPORTS_PER_DAY):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"每天最多导出 {_MAX_EXPORTS_PER_DAY} 次，请明天再试。",
        )

    try:
        zip_path = await export_user_data(db, user)
        _record_rate_limit(_export_counts, user.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出失败：{exc}",
        ) from exc

    timestamp = _utc_now().strftime("%Y%m%d")
    filename = f"export_{timestamp}_{user.username}.dra"

    return FileResponse(
        path=zip_path,
        filename=filename,
        media_type="application/octet-stream",
        background=None,
    )


def _ensure_import_allowed(user: User, filename: str | None, file_size: int | None = None) -> None:
    if not _check_rate_limit(_import_counts, user.id, _MAX_IMPORTS_PER_DAY):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"每天最多导入 {_MAX_IMPORTS_PER_DAY} 次，请明天再试。",
        )

    if not filename or not filename.endswith(".dra"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .dra 格式的导出包。",
        )

    if file_size is not None and file_size > _MAX_IMPORT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="导出包大小超过 1GB 限制。",
        )

    _check_active_import(user.id)


def _start_import_from_path(user: User, filename: str, tmp_path: Path) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    now = _utc_now().isoformat()
    with _import_task_lock:
        _import_tasks[job_id] = {
            "job_id": job_id,
            "user_id": user.id,
            "filename": filename,
            "status": "pending",
            "progress": 0,
            "current_stage": "等待后台导入任务启动...",
            "error_msg": None,
            "result": None,
            "created_at": now,
            "updated_at": now,
            "finished_at": None,
        }
        _user_active_imports[user.id] = job_id

    thread = threading.Thread(target=_run_import_task, args=(job_id, user.id, tmp_path), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "pending", "message": "导入任务已开始。"}


async def _start_import_data(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Start an async user data import from a .dra zip package.

    WARNING: This will CLEAR all existing user data before importing.
    """
    _ensure_import_allowed(user, file.filename)

    contents = await file.read()
    if len(contents) > _MAX_IMPORT_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="导出包大小超过 1GB 限制。",
        )

    tmp_path = Path(tempfile.mktemp(suffix=".dra"))
    try:
        with open(tmp_path, "wb") as f:
            f.write(contents)
    except HTTPException:
        raise
    except Exception as exc:
        if tmp_path.exists():
            os.unlink(tmp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入任务创建失败：{exc}",
        ) from exc

    return _start_import_from_path(user, file.filename, tmp_path)


@router.post("/import/chunk/init")
async def import_chunk_init(
    filename: str = Form(...),
    total_size: int = Form(...),
    total_chunks: int = Form(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    _ensure_import_allowed(user, filename, total_size)
    if total_chunks <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分片数量无效。")

    upload_id = str(uuid.uuid4())
    upload_dir = Path(tempfile.mkdtemp(prefix=f"import_upload_{user.id}_{upload_id}_"))
    now = _utc_now().isoformat()
    with _import_upload_lock:
        _import_upload_sessions[upload_id] = {
            "upload_id": upload_id,
            "user_id": user.id,
            "filename": filename,
            "total_size": total_size,
            "total_chunks": total_chunks,
            "upload_dir": str(upload_dir),
            "received": set(),
            "created_at": now,
            "updated_at": now,
        }
    return {"upload_id": upload_id}


@router.post("/import/chunk")
async def import_chunk_upload(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    with _import_upload_lock:
        session = _import_upload_sessions.get(upload_id)
        if session is None or session.get("user_id") != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分片上传会话不存在。")
        total_chunks = int(session["total_chunks"])
        upload_dir = Path(str(session["upload_dir"]))

    if chunk_index < 0 or chunk_index >= total_chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分片序号无效。")

    contents = await chunk.read()
    if len(contents) > _IMPORT_CHUNK_SIZE_LIMIT:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="单个分片超过 10MB。")

    chunk_path = upload_dir / f"{chunk_index:08d}.part"
    try:
        with open(chunk_path, "wb") as f:
            f.write(contents)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"保存分片失败：{exc}") from exc

    with _import_upload_lock:
        session = _import_upload_sessions.get(upload_id)
        if session is None or session.get("user_id") != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分片上传会话不存在。")
        session["received"].add(chunk_index)
        session["updated_at"] = _utc_now().isoformat()
        received_count = len(session["received"])

    return {"upload_id": upload_id, "received": received_count, "total_chunks": total_chunks}


@router.post("/import/chunk/complete")
async def import_chunk_complete(
    upload_id: str = Form(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    with _import_upload_lock:
        session = _import_upload_sessions.get(upload_id)
        if session is None or session.get("user_id") != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="分片上传会话不存在。")
        filename = str(session["filename"])
        total_size = int(session["total_size"])
        total_chunks = int(session["total_chunks"])
        received = set(session["received"])
        upload_dir = Path(str(session["upload_dir"]))

    _ensure_import_allowed(user, filename, total_size)
    missing = [idx for idx in range(total_chunks) if idx not in received]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"分片尚未上传完成：缺少 {len(missing)} 个。")

    tmp_path = Path(tempfile.mktemp(suffix=".dra"))
    try:
        written = 0
        with open(tmp_path, "wb") as out:
            for idx in range(total_chunks):
                chunk_path = upload_dir / f"{idx:08d}.part"
                data = chunk_path.read_bytes()
                written += len(data)
                out.write(data)
        if written != total_size:
            raise ValueError(f"文件大小不匹配，预期 {total_size} 字节，实际 {written} 字节。")
    except Exception as exc:
        if tmp_path.exists():
            os.unlink(tmp_path)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"组装导入包失败：{exc}") from exc
    finally:
        with _import_upload_lock:
            _import_upload_sessions.pop(upload_id, None)
        import shutil
        shutil.rmtree(upload_dir, ignore_errors=True)

    return _start_import_from_path(user, filename, tmp_path)


@router.post("/import")
async def import_data(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    return await _start_import_data(file=file, user=user)


@router.post("/import/start")
async def import_data_start(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    return await _start_import_data(file=file, user=user)


@router.get("/import/{job_id}/status")
async def import_data_status(
    job_id: str,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    with _import_task_lock:
        task = _import_tasks.get(job_id)
        if task is None or task.get("user_id") != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="导入任务不存在。")
        return {
            "job_id": task["job_id"],
            "status": task["status"],
            "progress": task["progress"],
            "current_stage": task["current_stage"],
            "error_msg": task["error_msg"],
            "result": task["result"],
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
            "finished_at": task["finished_at"],
        }
