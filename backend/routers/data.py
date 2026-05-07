"""Data export/import router for user data portability (.dra format)."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import get_db
from db.models import User
from services.data_portability import export_user_data, import_user_data

router = APIRouter()

# Simple in-memory rate limiting
_export_counts: dict[int, list[datetime]] = {}
_import_counts: dict[int, list[datetime]] = {}

_MAX_EXPORTS_PER_DAY = 5
_MAX_IMPORTS_PER_DAY = 3


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


@router.post("/import")
async def import_data(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Import user data from a .dra zip package.

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

    # Size check (1GB max)
    MAX_SIZE = 1024 * 1024 * 1024
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="导出包大小超过 1GB 限制。",
        )

    # Write to temp file
    import tempfile

    tmp_path = Path(tempfile.mktemp(suffix=".dra"))
    try:
        with open(tmp_path, "wb") as f:
            f.write(contents)

        result = await import_user_data(db, user, tmp_path)
        _record_rate_limit(_import_counts, user.id)
        return {
            "success": True,
            "message": "导入成功。",
            "cleared": result["cleared"],
            "imported": result["imported"],
            "files_restored": result["files_restored"],
            "files_missing": result["files_missing"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入失败：{exc}",
        ) from exc
    finally:
        if tmp_path.exists():
            os.unlink(tmp_path)
