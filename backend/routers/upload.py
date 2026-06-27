"""Upload Router - authenticated, user-isolated file uploads."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File as FastAPIFile, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import get_db
from db.models import BibEntry, File, Job, User
from db.utils import title_match_score
from services.markdown_library_import import import_markdown_file_to_library
from services.markdown_preview import render_markdown_preview_html
from upload_storage import build_storage_path, get_user_upload_dir, resolve_storage_path


router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".doc", ".docx", ".md", ".markdown"}
SOURCE_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "markdown": "text/markdown; charset=utf-8",
}


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def detect_file_type(filename: str, sample: bytes) -> str:
    file_ext = Path(filename).suffix.lower()
    if file_ext == ".pdf":
        return "pdf"
    if file_ext in {".doc", ".docx"}:
        return "docx"
    if file_ext in {".md", ".markdown"}:
        return "markdown"
    if file_ext == ".txt":
        preview = sample.decode("utf-8", errors="ignore").lower()
        bibliography_markers = (
            "wos",
            "web of science",
            "cnki",
            "issn",
            "\nau ",
            "\nti ",
            "\npy ",
            "作者",
            "篇名",
            "关键词",
            "来源数据库",
        )
        if any(marker in preview for marker in bibliography_markers):
            return "bibliography"
        return "txt"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的文件类型。")


def compute_expires_at_for_role(role: str) -> datetime | None:
    if role == "normal":
        return utcnow_naive() + timedelta(hours=24)
    return None


def compute_expires_at(user: User) -> datetime | None:
    return compute_expires_at_for_role(user.role)


async def persist_upload_to_temp(file: UploadFile, temp_path: Path) -> tuple[str, int, bytes]:
    hasher = hashlib.md5()
    size_bytes = 0
    sample = b""

    with temp_path.open("wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            if not sample:
                sample = chunk[:4096]
            hasher.update(chunk)
            buffer.write(chunk)
            size_bytes += len(chunk)

    if size_bytes == 0:
        if temp_path.exists():
            temp_path.unlink()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持空文件上传。")

    return hasher.hexdigest(), size_bytes, sample


async def find_matching_bib_entry(db: AsyncSession, user_id: int, title: str) -> BibEntry | None:
    title = (title or "").strip()
    if not title:
        return None

    candidates = (
        await db.execute(
            select(BibEntry).where(BibEntry.owner_user_id == user_id).order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc())
        )
    ).scalars().all()

    best_entry: BibEntry | None = None
    best_score = 0.0
    for candidate in candidates:
        score = title_match_score(title, candidate.title or "")
        if score > best_score:
            best_score = score
            best_entry = candidate

    if best_entry is None:
        return None
    if best_score >= 0.92:
        return best_entry
    if best_score >= 0.72:
        return best_entry
    return None


def snapshot_bib_match(matched_bib: BibEntry | None) -> dict[str, str] | None:
    if matched_bib is None:
        return None
    return {
        "id": matched_bib.id,
        "title": matched_bib.title,
    }


def snapshot_file_record(record: File) -> dict:
    return {
        "file_id": record.id,
        "filename": record.original_name,
        "size": record.size_bytes,
        "type": record.file_type,
        "storage_path": record.storage_path,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
    }


def build_upload_response_from_snapshot(
    record: dict,
    *,
    message: str,
    deduplicated: bool,
    matched_bib: dict[str, str] | None = None,
) -> dict:
    stored_file_path = resolve_storage_path(record["storage_path"])
    return {
        "success": True,
        "file_id": record["file_id"],
        "filename": record["filename"],
        "size": record["size"],
        "type": record["type"],
        "storage_path": record["storage_path"],
        "expires_at": record["expires_at"],
        "exists": stored_file_path.exists(),
        "deduplicated": deduplicated,
        "message": message,
        "matched_bib_entry_id": matched_bib["id"] if matched_bib else None,
        "matched_bib_title": matched_bib["title"] if matched_bib else None,
    }


async def bind_uploaded_file_to_existing_bib(db: AsyncSession, user_id: int, record: File) -> BibEntry | None:
    if record.file_type not in {"pdf", "markdown"}:
        return None

    if record.file_type == "markdown":
        imported = await import_markdown_file_to_library(db, owner_user_id=user_id, record=record)
        if imported is not None:
            return imported

    title = Path(record.original_name or "").stem
    matched = await find_matching_bib_entry(db, user_id, title)
    if matched is None:
        return None

    if record.file_type == "markdown" and not matched.markdown_source_file_id:
        matched.markdown_source_file_id = record.id
    if not matched.source_file_id:
        matched.source_file_id = record.id
    if matched.reading_status == "none":
        matched.reading_status = "has_pdf"
    matched.updated_at = utcnow_naive()
    return matched


def build_upload_response(
    record: File,
    *,
    message: str,
    deduplicated: bool,
    matched_bib: dict[str, str] | None = None,
) -> dict:
    stored_file_path = resolve_storage_path(record.storage_path)
    return {
        "success": True,
        "file_id": record.id,
        "filename": record.original_name,
        "size": record.size_bytes,
        "type": record.file_type,
        "storage_path": record.storage_path,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "exists": stored_file_path.exists(),
        "deduplicated": deduplicated,
        "message": message,
        "matched_bib_entry_id": matched_bib["id"] if matched_bib else None,
        "matched_bib_title": matched_bib["title"] if matched_bib else None,
    }


@router.post("/")
async def upload_file(
    file: UploadFile = FastAPIFile(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file into the authenticated user's isolated directory."""
    user_id = user.id
    user_role = user.role
    original_name = (file.filename or "").strip()
    if not original_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="缺少文件名。")

    file_ext = Path(original_name).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file_ext}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    user_dir = get_user_upload_dir(user_id)
    temp_path = user_dir / f".{uuid.uuid4()}.uploading"
    final_path: Path | None = None

    try:
        md5_hash, size_bytes, sample = await persist_upload_to_temp(file, temp_path)
        file_type = detect_file_type(original_name, sample)

        existing = (
            await db.execute(
                select(File).where(File.owner_user_id == user_id, File.md5 == md5_hash)
            )
        ).scalar_one_or_none()
        if existing is not None:
            matched_bib = await bind_uploaded_file_to_existing_bib(db, user_id, existing)
            matched_bib_snapshot = snapshot_bib_match(matched_bib)
            existing_snapshot = snapshot_file_record(existing)
            await db.commit()
            if temp_path.exists():
                temp_path.unlink()
            return build_upload_response_from_snapshot(
                existing_snapshot,
                message="文件已存在，返回已有记录。",
                deduplicated=True,
                matched_bib=matched_bib_snapshot,
            )

        file_id = str(uuid.uuid4())
        final_path, storage_path = build_storage_path(user_id, file_id, file_ext)
        shutil.move(str(temp_path), str(final_path))
        expires_at = compute_expires_at_for_role(user_role)

        record = File(
            id=file_id,
            owner_user_id=user_id,
            original_name=original_name,
            file_type=file_type,
            storage_path=storage_path,
            size_bytes=size_bytes,
            md5=md5_hash,
            expires_at=expires_at,
        )
        db.add(record)
        # PostgreSQL enforces the FK immediately, so the new file row must exist
        # before we point a matched bib entry at record.id.
        await db.flush()
        matched_bib = await bind_uploaded_file_to_existing_bib(db, user_id, record)
        matched_bib_snapshot = snapshot_bib_match(matched_bib)
        record_snapshot = {
            "file_id": file_id,
            "filename": original_name,
            "size": size_bytes,
            "type": file_type,
            "storage_path": storage_path,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = (
                await db.execute(
                    select(File).where(File.owner_user_id == user_id, File.md5 == md5_hash)
                )
            ).scalar_one_or_none()
            if existing is None:
                raise
            if final_path.exists():
                final_path.unlink()
            return build_upload_response_from_snapshot(
                snapshot_file_record(existing),
                message="文件已存在，返回已有记录。",
                deduplicated=True,
                matched_bib=matched_bib_snapshot,
            )

        return build_upload_response_from_snapshot(
            record_snapshot,
            message="上传成功。",
            deduplicated=False,
            matched_bib=matched_bib_snapshot,
        )
    except HTTPException:
        if temp_path.exists():
            temp_path.unlink()
        raise
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink()
        if final_path is not None and final_path.exists():
            final_path.unlink()
        logger.exception("Upload failed for user=%s filename=%s", user_id, original_name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {exc}",
        ) from exc
    finally:
        await file.close()


@router.get("/{file_id}/info")
async def get_file_info(
    file_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get info for a file owned by the current user."""
    record = (
        await db.execute(select(File).where(File.id == file_id, File.owner_user_id == user.id))
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return build_upload_response(record, message="查询成功。", deduplicated=False)


async def get_owned_source_file(
    file_id: str,
    user: User,
    db: AsyncSession,
) -> tuple[File, Path]:
    record = (
        await db.execute(select(File).where(File.id == file_id, File.owner_user_id == user.id))
    ).scalar_one_or_none()
    if record is None or record.file_type not in SOURCE_MEDIA_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found")

    stored_path = resolve_storage_path(record.storage_path)
    if not stored_path.exists() or not stored_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source file not found")
    return record, stored_path


@router.get("/{file_id}/preview")
async def preview_source_file(
    file_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    record, stored_path = await get_owned_source_file(file_id, user, db)
    if record.file_type == "markdown":
        return HTMLResponse(
            render_markdown_preview_html(
                stored_path.read_text(encoding="utf-8"),
                record.original_name,
            )
        )
    return FileResponse(
        stored_path,
        media_type=SOURCE_MEDIA_TYPES[record.file_type],
        headers={"Content-Disposition": "inline"},
    )


@router.get("/{file_id}/download")
async def download_source_file(
    file_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    record, stored_path = await get_owned_source_file(file_id, user, db)
    return FileResponse(
        stored_path,
        filename=record.original_name,
        media_type=SOURCE_MEDIA_TYPES[record.file_type],
    )


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an uploaded file owned by the current user when it has no active references."""
    record = (
        await db.execute(select(File).where(File.id == file_id, File.owner_user_id == user.id))
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    job_reference = (
        await db.execute(select(Job.id).where(Job.input_file_id == file_id).limit(1))
    ).scalar_one_or_none()
    if job_reference is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该文件已被任务引用，暂不能删除。",
        )

    bib_reference = (
        await db.execute(select(BibEntry.id).where(BibEntry.source_file_id == file_id).limit(1))
    ).scalar_one_or_none()
    if bib_reference is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该文件已绑定文献档案，暂不能删除。",
        )

    stored_path = resolve_storage_path(record.storage_path)
    if stored_path.exists():
        stored_path.unlink()

    await db.delete(record)
    await db.commit()

    user_dir = get_user_upload_dir(user.id)
    if user_dir.exists() and not any(user_dir.iterdir()):
        user_dir.rmdir()

    return {"success": True, "message": "File deleted"}
