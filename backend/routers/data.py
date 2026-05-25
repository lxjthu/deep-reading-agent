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

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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

_import_tasks: dict[str, dict[str, Any]] = {}
_user_active_imports: dict[int, str] = {}
_import_task_lock = threading.Lock()


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


async def _start_import_data(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    """Start an async user data import from a .dra zip package.

    WARNING: This will CLEAR all existing user data before importing.
    """
    if not _check_rate_limit(_import_counts, user.id, _MAX_IMPORTS_PER_DAY):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"每天最多导入 {_MAX_IMPORTS_PER_DAY} 次，请明天再试。",
        )

    # Validate file extension
    if not file.filename or not file.filename.endswith(".dra"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .dra 格式的导出包。",
        )

    with _import_task_lock:
        active_job_id = _user_active_imports.get(user.id)
        active_task = _import_tasks.get(active_job_id or "")
        if active_job_id and active_task and active_task.get("status") in {"pending", "running"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="已有导入任务正在运行，请等待完成后再导入。",
            )

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

    job_id = str(uuid.uuid4())
    now = _utc_now().isoformat()
    with _import_task_lock:
        _import_tasks[job_id] = {
            "job_id": job_id,
            "user_id": user.id,
            "filename": file.filename,
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
