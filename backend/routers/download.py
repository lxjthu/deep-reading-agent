"""
Download Router - File downloads for analysis results
"""
import os
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import get_db
from db.models import Artifact, Job, User

router = APIRouter()

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "deep_reading_results")


async def _resolve_download_artifact(
    db: AsyncSession,
    user: User,
    identifier: str,
) -> Artifact | None:
    normalized = identifier.replace("\\", "/").lstrip("/")

    exact_stmt = (
        select(Artifact)
        .join(Job, Job.id == Artifact.job_id)
        .where(Artifact.storage_path == normalized)
        .order_by(Artifact.created_at.desc(), Artifact.id.desc())
    )
    if user.role != "admin":
        exact_stmt = exact_stmt.where(Artifact.owner_user_id == user.id)
    artifact = (await db.execute(exact_stmt)).scalars().first()
    if artifact is not None:
        return artifact

    filename_stmt = (
        select(Artifact)
        .join(Job, Job.id == Artifact.job_id)
        .where(Artifact.filename == os.path.basename(identifier))
        .order_by(Artifact.created_at.desc(), Artifact.id.desc())
    )
    if user.role != "admin":
        filename_stmt = filename_stmt.where(Artifact.owner_user_id == user.id)
    return (await db.execute(filename_stmt)).scalars().first()


@router.get("/{file_path:path}")
async def download_file(
    file_path: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Download a result file by path.
    Path should be URL-encoded.
    """
    decoded_path = urllib.parse.unquote(file_path)

    artifact = await _resolve_download_artifact(db, user, decoded_path)
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    target_path = Path(RESULTS_DIR) / artifact.storage_path
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    ext = os.path.splitext(target_path)[1].lower()
    media_types = {
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.xls': 'application/vnd.ms-excel',
        '.md': 'text/markdown; charset=utf-8',
        '.txt': 'text/plain; charset=utf-8',
        '.pdf': 'application/pdf',
        '.csv': 'text/csv; charset=utf-8',
    }
    media_type = media_types.get(ext, 'application/octet-stream')
    
    return FileResponse(
        target_path,
        filename=artifact.filename,
        media_type=media_type
    )
