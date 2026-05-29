"""Retention helpers and scheduled cleanup for multi-user data."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete as sa_delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db import AsyncSessionLocal, DB_DIR, PROJECT_ROOT
from db.models import (
    AgentActionProposal,
    AgentMessage,
    AgentSession,
    Annotation,
    Artifact,
    BibEntry,
    BibFilterLink,
    BibReference,
    BibReferenceCitation,
    CardNote,
    DimensionItem,
    DimensionSet,
    File,
    Job,
    JobBibEntry,
    PromptTemplate,
    ReadingItem,
    ReadingItemEdit,
    RefFormatPreset,
    UploadBatch,
    UserFeedback,
)
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
    for model in (UploadBatch, File, BibEntry, Job, Artifact, CardNote):
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


def _resolve_result_storage_path(root: Path, storage_path: str | None) -> Path | None:
    if not storage_path:
        return None
    candidate = Path(storage_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate


def _count_existing_paths(paths: set[Path]) -> int:
    return sum(1 for path in paths if path.exists() and path.is_file())


def _delete_physical_paths(paths: set[Path]) -> int:
    deleted = 0
    for path in sorted(paths):
        if _remove_file_if_exists(path):
            deleted += 1
    return deleted


async def _scalar_count(db: AsyncSession, statement) -> int:
    return int((await db.execute(statement)).scalar_one() or 0)


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
        "card_notes_deleted": 0,
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

    expired_cards = (
        await db.execute(
            select(CardNote).where(CardNote.expires_at.is_not(None), CardNote.expires_at <= now)
        )
    ).scalars().all()
    for card in expired_cards:
        file_path = results_root / card.storage_path if card.storage_path else None
        if dry_run:
            stats["card_notes_deleted"] += 1
            if file_path and file_path.exists():
                stats["physical_files_deleted"] += 1
            continue
        if file_path and _remove_file_if_exists(file_path):
            stats["physical_files_deleted"] += 1
        await db.delete(card)
        stats["card_notes_deleted"] += 1

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
            await db.execute(sa_delete(ReadingItemEdit).where(ReadingItemEdit.reading_item_id.in_(
                select(ReadingItem.id).where(ReadingItem.bib_entry_id == bib.id)
            )))
            await db.execute(sa_delete(Annotation).where(Annotation.bib_entry_id == str(bib.id)))
            await db.execute(sa_delete(ReadingItem).where(ReadingItem.bib_entry_id == bib.id))
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
    from db.models import User

    stats = {
        "dry_run": dry_run,
        "agent_sessions_deleted": 0,
        "agent_messages_deleted": 0,
        "agent_action_proposals_deleted": 0,
        "prompt_templates_deleted": 0,
        "ref_format_presets_deleted": 0,
        "dimension_sets_deleted": 0,
        "dimension_items_deleted": 0,
        "bib_filter_links_deleted": 0,
        "job_bib_entries_deleted": 0,
        "bib_references_deleted": 0,
        "bib_reference_citations_deleted": 0,
        "bib_reference_matches_cleared": 0,
        "user_feedback_links_cleared": 0,
        "bib_cross_links_cleared": 0,
        "job_links_cleared": 0,
        "card_links_cleared": 0,
        "reading_items_deleted": 0,
        "reading_item_edits_deleted": 0,
        "annotations_deleted": 0,
        "artifacts_deleted": 0,
        "card_notes_deleted": 0,
        "jobs_deleted": 0,
        "bib_entries_deleted": 0,
        "files_deleted": 0,
        "upload_batches_deleted": 0,
        "physical_files_deleted": 0,
        "empty_dirs_deleted": 0,
        "users_affected": 0,
    }

    normal_users = (
        await db.execute(select(User).where(User.role == "normal"))
    ).scalars().all()
    normal_user_ids = [u.id for u in normal_users]
    stats["users_affected"] = len(normal_user_ids)

    if not normal_user_ids:
        log_cleanup("cleanup_normal_users dry_run={} no_normal_users".format(dry_run))
        return {**stats, "summary": "No normal users found."}

    results_root = get_results_root()

    normal_dim_set_ids = select(DimensionSet.id).where(DimensionSet.owner_user_id.in_(normal_user_ids))
    normal_job_ids = select(Job.id).where(Job.owner_user_id.in_(normal_user_ids))
    normal_bib_ids = select(BibEntry.id).where(BibEntry.owner_user_id.in_(normal_user_ids))
    normal_file_ids = select(File.id).where(File.owner_user_id.in_(normal_user_ids))
    normal_artifact_ids = select(Artifact.id).where(Artifact.owner_user_id.in_(normal_user_ids))

    physical_paths: set[Path] = set()
    artifact_storage_paths = (
        await db.execute(select(Artifact.storage_path).where(Artifact.owner_user_id.in_(normal_user_ids)))
    ).scalars().all()
    for storage_path in artifact_storage_paths:
        resolved = _resolve_result_storage_path(results_root, storage_path)
        if resolved is not None:
            physical_paths.add(resolved)

    card_storage_paths = (
        await db.execute(select(CardNote.storage_path).where(CardNote.owner_user_id.in_(normal_user_ids)))
    ).scalars().all()
    for storage_path in card_storage_paths:
        resolved = _resolve_result_storage_path(results_root, storage_path)
        if resolved is not None:
            physical_paths.add(resolved)

    file_storage_paths = (
        await db.execute(select(File.storage_path).where(File.owner_user_id.in_(normal_user_ids)))
    ).scalars().all()
    for storage_path in file_storage_paths:
        physical_paths.add(resolve_storage_path(storage_path))

    stats["physical_files_deleted"] = _count_existing_paths(physical_paths)

    stats["agent_sessions_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(AgentSession).where(AgentSession.owner_user_id.in_(normal_user_ids))
    )
    stats["agent_messages_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(AgentMessage).where(AgentMessage.owner_user_id.in_(normal_user_ids))
    )
    stats["agent_action_proposals_deleted"] = await _scalar_count(
        db,
        select(func.count()).select_from(AgentActionProposal).where(
            AgentActionProposal.owner_user_id.in_(normal_user_ids)
        ),
    )
    stats["prompt_templates_deleted"] = await _scalar_count(
        db,
        select(func.count()).select_from(PromptTemplate).where(PromptTemplate.owner_user_id.in_(normal_user_ids)),
    )
    stats["ref_format_presets_deleted"] = await _scalar_count(
        db,
        select(func.count()).select_from(RefFormatPreset).where(
            RefFormatPreset.owner_user_id.in_(normal_user_ids)
        ),
    )
    stats["dimension_sets_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(DimensionSet).where(DimensionSet.owner_user_id.in_(normal_user_ids))
    )
    stats["dimension_items_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(DimensionItem).where(DimensionItem.set_id.in_(normal_dim_set_ids))
    )
    stats["artifacts_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(Artifact).where(Artifact.owner_user_id.in_(normal_user_ids))
    )
    stats["card_notes_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(CardNote).where(CardNote.owner_user_id.in_(normal_user_ids))
    )
    stats["jobs_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(Job).where(Job.owner_user_id.in_(normal_user_ids))
    )
    stats["bib_filter_links_deleted"] = await _scalar_count(
        db,
        select(func.count()).select_from(BibFilterLink).where(
            BibFilterLink.filter_job_id.in_(normal_job_ids) | BibFilterLink.bib_entry_id.in_(normal_bib_ids)
        ),
    )
    stats["job_bib_entries_deleted"] = await _scalar_count(
        db,
        select(func.count()).select_from(JobBibEntry).where(
            JobBibEntry.job_id.in_(normal_job_ids) | JobBibEntry.bib_entry_id.in_(normal_bib_ids)
        ),
    )
    stats["reading_item_edits_deleted"] = await _scalar_count(
        db,
        select(func.count()).select_from(ReadingItemEdit).where(
            ReadingItemEdit.owner_user_id.in_(normal_user_ids)
        ),
    )
    stats["annotations_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(Annotation).where(Annotation.owner_user_id.in_(normal_user_ids))
    )
    stats["reading_items_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(ReadingItem).where(ReadingItem.owner_user_id.in_(normal_user_ids))
    )
    stats["bib_reference_citations_deleted"] = await _scalar_count(
        db,
        select(func.count()).select_from(BibReferenceCitation).where(
            BibReferenceCitation.owner_user_id.in_(normal_user_ids)
        ),
    )
    stats["bib_references_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(BibReference).where(BibReference.owner_user_id.in_(normal_user_ids))
    )
    stats["bib_reference_matches_cleared"] = await _scalar_count(
        db,
        select(func.count()).select_from(BibReference).where(BibReference.matched_bib_entry_id.in_(normal_bib_ids)),
    )
    stats["user_feedback_links_cleared"] = await _scalar_count(
        db,
        select(func.count()).select_from(UserFeedback).where(
            UserFeedback.related_job_id.in_(normal_job_ids)
            | UserFeedback.related_file_id.in_(normal_file_ids)
            | UserFeedback.related_bib_entry_id.in_(normal_bib_ids)
            | UserFeedback.related_artifact_id.in_(normal_artifact_ids)
        ),
    )
    stats["bib_cross_links_cleared"] = await _scalar_count(
        db,
        select(func.count()).select_from(BibEntry).where(
            BibEntry.source_filter_job_id.in_(normal_job_ids)
            | BibEntry.source_file_id.in_(normal_file_ids)
            | BibEntry.markdown_source_file_id.in_(normal_file_ids)
        ),
    )
    stats["job_links_cleared"] = await _scalar_count(
        db, select(func.count()).select_from(Job).where(Job.input_file_id.in_(normal_file_ids))
    )
    stats["card_links_cleared"] = await _scalar_count(
        db,
        select(func.count()).select_from(CardNote).where(
            CardNote.source_markdown_file_id.in_(normal_file_ids)
            | CardNote.source_translation_artifact_id.in_(normal_artifact_ids)
        ),
    )
    stats["bib_entries_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(BibEntry).where(BibEntry.owner_user_id.in_(normal_user_ids))
    )
    stats["files_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(File).where(File.owner_user_id.in_(normal_user_ids))
    )
    stats["upload_batches_deleted"] = await _scalar_count(
        db, select(func.count()).select_from(UploadBatch).where(UploadBatch.owner_user_id.in_(normal_user_ids))
    )

    if dry_run:
        await db.rollback()
    else:
        await db.execute(
            update(BibReference)
            .where(BibReference.matched_bib_entry_id.in_(normal_bib_ids))
            .values(matched_bib_entry_id=None, match_method=None, match_score=None)
        )
        await db.execute(
            update(UserFeedback)
            .where(
                UserFeedback.related_job_id.in_(normal_job_ids)
                | UserFeedback.related_file_id.in_(normal_file_ids)
                | UserFeedback.related_bib_entry_id.in_(normal_bib_ids)
                | UserFeedback.related_artifact_id.in_(normal_artifact_ids)
            )
            .values(
                related_job_id=None,
                related_file_id=None,
                related_bib_entry_id=None,
                related_artifact_id=None,
            )
        )
        await db.execute(
            update(BibEntry)
            .where(
                BibEntry.source_filter_job_id.in_(normal_job_ids)
                | BibEntry.source_file_id.in_(normal_file_ids)
                | BibEntry.markdown_source_file_id.in_(normal_file_ids)
            )
            .values(
                source_filter_job_id=None,
                source_file_id=None,
                markdown_source_file_id=None,
            )
        )
        await db.execute(
            update(Job)
            .where(Job.input_file_id.in_(normal_file_ids))
            .values(input_file_id=None)
        )
        await db.execute(
            update(CardNote)
            .where(
                CardNote.source_markdown_file_id.in_(normal_file_ids)
                | CardNote.source_translation_artifact_id.in_(normal_artifact_ids)
            )
            .values(source_markdown_file_id=None, source_translation_artifact_id=None)
        )
        await db.execute(sa_delete(AgentActionProposal).where(AgentActionProposal.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(AgentMessage).where(AgentMessage.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(AgentSession).where(AgentSession.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(PromptTemplate).where(PromptTemplate.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(RefFormatPreset).where(RefFormatPreset.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(DimensionItem).where(DimensionItem.set_id.in_(normal_dim_set_ids)))
        await db.execute(sa_delete(DimensionSet).where(DimensionSet.owner_user_id.in_(normal_user_ids)))
        await db.execute(
            sa_delete(BibReferenceCitation).where(BibReferenceCitation.owner_user_id.in_(normal_user_ids))
        )
        await db.execute(sa_delete(BibReference).where(BibReference.owner_user_id.in_(normal_user_ids)))
        await db.execute(
            sa_delete(BibFilterLink).where(
                BibFilterLink.filter_job_id.in_(normal_job_ids) | BibFilterLink.bib_entry_id.in_(normal_bib_ids)
            )
        )
        await db.execute(
            sa_delete(JobBibEntry).where(
                JobBibEntry.job_id.in_(normal_job_ids) | JobBibEntry.bib_entry_id.in_(normal_bib_ids)
            )
        )
        await db.execute(sa_delete(ReadingItemEdit).where(ReadingItemEdit.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(Annotation).where(Annotation.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(ReadingItem).where(ReadingItem.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(CardNote).where(CardNote.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(Artifact).where(Artifact.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(Job).where(Job.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(BibEntry).where(BibEntry.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(File).where(File.owner_user_id.in_(normal_user_ids)))
        await db.execute(sa_delete(UploadBatch).where(UploadBatch.owner_user_id.in_(normal_user_ids)))
        await db.commit()
        stats["physical_files_deleted"] = _delete_physical_paths(physical_paths)
        stats["empty_dirs_deleted"] += remove_empty_directories(get_upload_root())
        stats["empty_dirs_deleted"] += remove_empty_directories(get_results_root())

    summary = (
        "cleanup_normal_users dry_run={dry_run} users={users_affected} "
        "sessions={agent_sessions_deleted} messages={agent_messages_deleted} "
        "proposals={agent_action_proposals_deleted} refs={bib_references_deleted} "
        "ref_citations={bib_reference_citations_deleted} "
        "artifacts={artifacts_deleted} jobs={jobs_deleted} bib_entries={bib_entries_deleted} "
        "files={files_deleted} batches={upload_batches_deleted} physical_files={physical_files_deleted} "
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
