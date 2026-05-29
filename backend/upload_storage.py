"""Shared helpers for uploaded file storage and lookup."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db import PROJECT_ROOT, SYNC_DATABASE_URL
from db.models import File


def get_upload_root() -> Path:
    """Return the upload root, allowing tests to override it."""
    configured = os.getenv("UPLOAD_ROOT_DIR")
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            root = (PROJECT_ROOT / root).resolve()
    else:
        root = PROJECT_ROOT / "_uploads"
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_user_upload_dir(user_id: int) -> Path:
    directory = get_upload_root() / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_storage_path(user_id: int, file_id: str, file_ext: str) -> tuple[Path, str]:
    suffix = file_ext if file_ext.startswith(".") else f".{file_ext}"
    absolute_path = get_user_upload_dir(user_id) / f"{file_id}{suffix}"
    try:
        relative_path = absolute_path.relative_to(PROJECT_ROOT)
        storage_path = relative_path.as_posix()
    except ValueError:
        storage_path = absolute_path.as_posix()
    return absolute_path, storage_path


def resolve_storage_path(storage_path: str) -> Path:
    path = Path(storage_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def storage_path_exists(storage_path: str | None) -> bool:
    if not storage_path:
        return False
    path = resolve_storage_path(storage_path)
    return path.exists() and path.is_file()


def file_record_exists(record: File | None) -> bool:
    if record is None:
        return False
    return storage_path_exists(record.storage_path)


def lookup_path_by_file_id(file_id: str) -> Optional[Path]:
    """Resolve the path for a file_id, preferring DB storage_path."""
    engine = create_engine(SYNC_DATABASE_URL)
    try:
        with Session(engine) as session:
            record = session.execute(select(File).where(File.id == file_id)).scalar_one_or_none()
            if record is not None:
                return resolve_storage_path(record.storage_path)
    finally:
        engine.dispose()

    for root, _, files in os.walk(get_upload_root()):
        for filename in files:
            if filename.startswith(file_id):
                return Path(root) / filename
    return None


def lookup_original_name(file_id: str) -> Optional[str]:
    engine = create_engine(SYNC_DATABASE_URL)
    try:
        with Session(engine) as session:
            record = session.execute(select(File).where(File.id == file_id)).scalar_one_or_none()
            if record is not None:
                return record.original_name
    finally:
        engine.dispose()
    return None
