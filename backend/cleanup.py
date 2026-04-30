"""Retention helpers and scheduled cleanup for multi-user data."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db import AsyncSessionLocal, DB_DIR, PROJECT_ROOT
from db.models import Artifact, BibEntry, File, Job, UploadBatch
from upload_storage import get_upload_root, resolve_storage_path


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_results_root() -> Path:
    configured = os.getenv("RESULTS_ROOT_DIR")
    root = Path(configured) if configured else (PROJECT_ROOT / "deep_reading_results")
    if not root.is_absolute():
        root = (PROJECT_ROOT / root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def parse_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_cleanup_interval_minutes() -> int:
    try:
        return max(1, int(os.getenv("CLEANUP_INTERVAL_MINUTES", "60")))
    except ValueError:
        return 60


def get_cleanup_log_path() -> Path:
    return DB_DIR / "cleanup.log"


def log_cleanup(message: str) -> None:
    timestamp = utcnow_naive().isoformat(sep=" ", timespec="seconds")
    log_path = get_cleanup_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{timestamp}] {message}\n")


def compute_expires_at_for_role(role: str, now: datetime | None = None) -> datetime | None:
    if role == "normal":
        return (now or utcnow_naive()) + timedelta(hours=24)
    return None


async def reapply_user_retention(
    db: AsyncSession,
    user_id: int,
    role: str,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Recompute expires_at for all user-owned records after a role change."""
    expires_at = compute_expires_at_for_role(role, now)
    for model in (UploadBatch, File, BibEntry, Job, Artifact):
        await db.execute(
            update(model)
            .where(model.owner_user_id == user_id)
            .values(expires_at=expires_at)
        )
    return expires_at


def _remove_file_if_exists(path: Path) -> bool:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except FileNotFoundError:
        return False
    return False


def remove_empty_directories(root: Path) -> int:
    removed = 0
    if not root.exists():
        return removed
    candidates = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for current in candidates:
        if current == root:
            continue
        try:
            next(current.iterdir())
            is_empty = False
        except StopIteration:
            is_empty = True
        if is_empty:
            try:
                current.rmdir()
                removed += 1
            except OSError:
                pass
    return removed


async def _cleanup_with_session(
    db: AsyncSession,
    *,
    now: datetime,
    dry_run: bool,
) -> dict[str, Any]:
    stats = {
        "dry_run": dry_run,
        "artifacts_deleted": 0,
        "jobs_deleted": 0,
        "bib_entries_deleted": 0,
        "files_deleted": 0,
        "upload_batches_deleted": 0,
        "physical_files_deleted": 0,
        "empty_dirs_deleted": 0,
    }

    expired_artifacts = (
        await db.execute(
            select(Artifact).where(Artifact.expires_at.is_not(None), Artifact.expires_at <= now)
        )
    ).scalars().all()
    results_root = get_results_root()
    for artifact in expired_artifacts:
        file_path = results_root / artifact.storage_path
        if dry_run:
            stats["artifacts_deleted"] += 1
            if file_path.exists():
                stats["physical_files_deleted"] += 1
            continue
        if _remove_file_if_exists(file_path):
            stats["physical_files_deleted"] += 1
        await db.delete(artifact)
        stats["artifacts_deleted"] += 1

    expired_jobs = (
        await db.execute(
            select(Job).where(Job.expires_at.is_not(None), Job.expires_at <= now)
        )
    ).scalars().all()
    for job in expired_jobs:
        if not dry_run:
            await db.delete(job)
        stats["jobs_deleted"] += 1

    expired_bibs = (
        await db.execute(
            select(BibEntry).where(BibEntry.expires_at.is_not(None), BibEntry.expires_at <= now)
        )
    ).scalars().all()
    for bib in expired_bibs:
        if not dry_run:
            await db.delete(bib)
        stats["bib_entries_deleted"] += 1

    expired_files = (
        await db.execute(
            select(File).where(File.expires_at.is_not(None), File.expires_at <= now)
        )
    ).scalars().all()
    for record in expired_files:
        physical_path = resolve_storage_path(record.storage_path)
        if dry_run:
            stats["files_deleted"] += 1
            if physical_path.exists():
                stats["physical_files_deleted"] += 1
            continue
        if _remove_file_if_exists(physical_path):
            stats["physical_files_deleted"] += 1
        await db.delete(record)
        stats["files_deleted"] += 1

    expired_batches = (
        await db.execute(
            select(UploadBatch).where(
                UploadBatch.expires_at.is_not(None), UploadBatch.expires_at <= now
            )
        )
    ).scalars().all()
    for batch in expired_batches:
        if not dry_run:
            await db.delete(batch)
        stats["upload_batches_deleted"] += 1

    if dry_run:
        await db.rollback()
    else:
        await db.commit()
        stats["empty_dirs_deleted"] += remove_empty_directories(get_upload_root())
        stats["empty_dirs_deleted"] += remove_empty_directories(get_results_root())

    summary = (
        "cleanup dry_run={dry_run} artifacts={artifacts_deleted} jobs={jobs_deleted} "
        "bib_entries={bib_entries_deleted} files={files_deleted} batches={upload_batches_deleted} "
        "physical_files={physical_files_deleted} empty_dirs={empty_dirs_deleted}"
    ).format(**stats)
    log_cleanup(summary)
    stats["summary"] = summary
    return stats


async def cleanup_normal_user_data(
    *,
    dry_run: bool | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Remove ALL normal-user data from DB and disk. Runs at 00:00 daily."""
    effective_dry_run = parse_bool_env("CLEANUP_DRY_RUN", False) if dry_run is None else dry_run

    if db is not None:
        return await _cleanup_normal_with_session(db, dry_run=effective_dry_run)

    async with AsyncSessionLocal() as session:
        return await _cleanup_normal_with_session(session, dry_run=effective_dry_run)


async def _cleanup_normal_with_session(
    db: AsyncSession,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Delete all records owned by users with role='normal', plus physical files."""
    from sqlalchemy import select as sa_select
    stats = {
        "dry_run": dry_run,
        "artifacts_deleted": 0,
        "jobs_deleted": 0,
        "bib_entries_deleted": 0,
        "files_deleted": 0,
        "upload_batches_deleted": 0,
        "physical_files_deleted": 0,
        "empty_dirs_deleted": 0,
        "users_affected": 0,
    }

    # Find all normal users
    from db.models import User
    normal_users = (
        await db.execute(sa_select(User).where(User.role == "normal"))
    ).scalars().all()
    normal_user_ids = [u.id for u in normal_users]
    stats["users_affected"] = len(normal_user_ids)

    if not normal_user_ids:
        log_cleanup("cleanup_normal_users dry_run={} no_normal_users".format(dry_run))
        return {**stats, "summary": "No normal users found."}

    results_root = get_results_root()

    # 1. Artifacts
    artifacts = (
        await db.execute(
            sa_select(Artifact).where(Artifact.owner_user_id.in_(normal_user_ids))
        )
    ).scalars().all()
    for artifact in artifacts:
        file_path = results_root / artifact.storage_path
        if dry_run:
            stats["artifacts_deleted"] += 1
            if file_path.exists():
                stats["physical_files_deleted"] += 1
            continue
        if _remove_file_if_exists(file_path):
            stats["physical_files_deleted"] += 1
        await db.delete(artifact)
        stats["artifacts_deleted"] += 1

    # 2. Jobs
    jobs = (
        await db.execute(
            sa_select(Job).where(Job.owner_user_id.in_(normal_user_ids))
        )
    ).scalars().all()
    for job in jobs:
        if not dry_run:
            await db.delete(job)
        stats["jobs_deleted"] += 1

    # 3. BibEntries
    bibs = (
        await db.execute(
            sa_select(BibEntry).where(BibEntry.owner_user_id.in_(normal_user_ids))
        )
    ).scalars().all()
    for bib in bibs:
        if not dry_run:
            await db.delete(bib)
        stats["bib_entries_deleted"] += 1

    # 4. Files (with physical cleanup)
    files = (
        await db.execute(
            sa_select(File).where(File.owner_user_id.in_(normal_user_ids))
        )
    ).scalars().all()
    for record in files:
        physical_path = resolve_storage_path(record.storage_path)
        if dry_run:
            stats["files_deleted"] += 1
            if physical_path.exists():
                stats["physical_files_deleted"] += 1
            continue
        if _remove_file_if_exists(physical_path):
            stats["physical_files_deleted"] += 1
        await db.delete(record)
        stats["files_deleted"] += 1

    # 5. UploadBatches
    batches = (
        await db.execute(
            sa_select(UploadBatch).where(UploadBatch.owner_user_id.in_(normal_user_ids))
        )
    ).scalars().all()
    for batch in batches:
        if not dry_run:
            await db.delete(batch)
        stats["upload_batches_deleted"] += 1

    if dry_run:
        await db.rollback()
    else:
        await db.commit()
        stats["empty_dirs_deleted"] += remove_empty_directories(get_upload_root())
        stats["empty_dirs_deleted"] += remove_empty_directories(get_results_root())

    summary = (
        "cleanup_normal_users dry_run={dry_run} users={users_affected} "
        "artifacts={artifacts_deleted} jobs={jobs_deleted} "
        "bib_entries={bib_entries_deleted} files={files_deleted} "
        "batches={upload_batches_deleted} physical_files={physical_files_deleted} "
        "empty_dirs={empty_dirs_deleted}"
    ).format(**stats)
    log_cleanup(summary)
    stats["summary"] = summary
    return stats


# Legacy: keep for backward compat, but not used by scheduler
async def cleanup_expired(
    *,
    now: datetime | None = None,
    dry_run: bool | None = None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """Remove expired normal-user data from DB and disk. (Legacy)"""
    effective_now = now or utcnow_naive()
    effective_dry_run = parse_bool_env("CLEANUP_DRY_RUN", False) if dry_run is None else dry_run

    if db is not None:
        return await _cleanup_with_session(db, now=effective_now, dry_run=effective_dry_run)

    async with AsyncSessionLocal() as session:
        return await _cleanup_with_session(session, now=effective_now, dry_run=effective_dry_run)
