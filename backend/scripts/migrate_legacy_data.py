"""Migrate pre-multiuser legacy files into admin-owned storage and DB records."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
PROJECT_ROOT = BACKEND_DIR.parent
for path in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy import select  # noqa: E402

from db import AsyncSessionLocal  # noqa: E402
from db.models import Artifact, BibEntry, File, Job, User  # noqa: E402
from upload_storage import build_storage_path, get_upload_root  # noqa: E402

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def get_results_root() -> Path:
    configured = os.getenv("RESULTS_ROOT_DIR")
    root = Path(configured) if configured else (PROJECT_ROOT / "deep_reading_results")
    if not root.is_absolute():
        root = (PROJECT_ROOT / root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def compute_md5(path: Path) -> str:
    hasher = hashlib.md5()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_legacy_file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".md", ".markdown"}:
        return "markdown"
    if ext in {".doc", ".docx"}:
        return "docx"
    if ext in {".xls", ".xlsx"}:
        return "bibliography"
    if ext == ".txt":
        return "txt"
    raise ValueError(f"Unsupported legacy file extension: {path.name}")


def build_result_storage_path(results_root: Path, absolute_path: Path) -> str:
    return absolute_path.relative_to(results_root).as_posix()


def is_new_upload_layout(path: Path, upload_root: Path) -> bool:
    relative = path.relative_to(upload_root)
    return len(relative.parts) >= 2 and relative.parts[0].isdigit()


def is_new_results_layout(path: Path, results_root: Path) -> bool:
    relative = path.relative_to(results_root)
    return len(relative.parts) >= 3 and relative.parts[0].isdigit()


def classify_result_file(relative_path: Path) -> tuple[str, str, str]:
    parts = relative_path.parts
    filename = relative_path.name
    lower_name = filename.lower()
    if parts and parts[0] == "literature_filter":
        return ("filter", "filter_excel", f"filter:{relative_path.as_posix()}")
    if parts and parts[0] == "synthesis":
        return ("synthesis", "synthesis_md", f"synthesis:{relative_path.as_posix()}")
    if "step_" in lower_name:
        return ("reading_quant", "reading_step", f"reading:{parts[0] if parts else 'legacy'}")
    return ("reading_long", "reading_final", f"reading:{parts[0] if parts else 'legacy'}")


@dataclass
class MigrationStats:
    migrated_uploads: int = 0
    migrated_results: int = 0
    created_files: int = 0
    created_jobs: int = 0
    created_artifacts: int = 0
    created_bib_entries: int = 0
    skipped_structured: int = 0
    planned_moves: int = 0


async def ensure_admin(session) -> User:
    admin = (
        await session.execute(select(User).where(User.username == ADMIN_USERNAME))
    ).scalar_one_or_none()
    if admin is not None:
        return admin
    admin = User(
        username=ADMIN_USERNAME,
        password_hash="legacy-admin-placeholder",
        role="admin",
        is_active=1,
        token_version=0,
        created_at=utcnow_naive(),
    )
    session.add(admin)
    await session.flush()
    return admin


async def maybe_create_minimal_bib(
    session,
    admin_id: int,
    record: File,
    stats: MigrationStats,
    *,
    dry_run: bool,
) -> None:
    if record.file_type not in {"pdf", "markdown"}:
        return
    if dry_run:
        stats.created_bib_entries += 1
        return

    source_db = "pdf_extracted" if record.file_type == "pdf" else "md_extracted"
    reading_status = "has_pdf" if record.file_type in {"pdf", "markdown"} else "none"
    bib = BibEntry(
        id=str(uuid.uuid4()),
        owner_user_id=admin_id,
        title=Path(record.original_name).stem,
        authors_json="[]",
        source_db=source_db,
        source_filter_job_id=None,
        source_file_id=record.id,
        reading_status=reading_status,
        metadata_completeness="minimal",
        dedup_key=f"legacy-file:{record.id}",
        keywords_json="[]",
        user_tags_json="[]",
        created_at=utcnow_naive(),
        updated_at=utcnow_naive(),
        expires_at=None,
    )
    session.add(bib)
    stats.created_bib_entries += 1


async def migrate_uploads(session, admin: User, *, dry_run: bool, stats: MigrationStats) -> None:
    upload_root = get_upload_root()
    for path in sorted(upload_root.rglob("*")):
        if not path.is_file():
            continue
        if is_new_upload_layout(path, upload_root):
            stats.skipped_structured += 1
            continue

        file_type = detect_legacy_file_type(path)
        file_id = str(uuid.uuid4())
        absolute_target, storage_path = build_storage_path(admin.id, file_id, path.suffix.lower())
        record = File(
            id=file_id,
            owner_user_id=admin.id,
            original_name=path.name,
            file_type=file_type,
            storage_path=storage_path,
            size_bytes=path.stat().st_size,
            md5=compute_md5(path),
            batch_id=None,
            created_at=utcnow_naive(),
            expires_at=None,
        )
        stats.planned_moves += 1
        stats.migrated_uploads += 1
        stats.created_files += 1

        if dry_run:
            await maybe_create_minimal_bib(session, admin.id, record, stats, dry_run=True)
            continue

        absolute_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(absolute_target))
        session.add(record)
        await maybe_create_minimal_bib(session, admin.id, record, stats, dry_run=False)


async def migrate_results(session, admin: User, *, dry_run: bool, stats: MigrationStats) -> None:
    results_root = get_results_root()
    job_cache: dict[str, str] = {}
    for path in sorted(results_root.rglob("*")):
        if not path.is_file():
            continue
        if is_new_results_layout(path, results_root):
            stats.skipped_structured += 1
            continue

        relative_path = path.relative_to(results_root)
        job_type, artifact_type, group_key = classify_result_file(relative_path)
        job_id = job_cache.get(group_key)
        if job_id is None:
            job_id = str(uuid.uuid4())
            job_cache[group_key] = job_id
            stats.created_jobs += 1
            if not dry_run:
                session.add(
                    Job(
                        id=job_id,
                        owner_user_id=admin.id,
                        job_type=job_type,
                        status="success",
                        input_file_id=None,
                        params_json=json.dumps({"legacy_source": relative_path.as_posix()}, ensure_ascii=False),
                        progress=100,
                        current_stage="Legacy migration",
                        created_at=utcnow_naive(),
                        started_at=utcnow_naive(),
                        finished_at=utcnow_naive(),
                        expires_at=None,
                    )
                )

        target_path = results_root / str(admin.id) / job_id / path.name
        storage_path = build_result_storage_path(results_root, target_path)
        stats.planned_moves += 1
        stats.migrated_results += 1
        stats.created_artifacts += 1

        if dry_run:
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(target_path))
        session.add(
            Artifact(
                job_id=job_id,
                owner_user_id=admin.id,
                artifact_type=artifact_type,
                filename=path.name,
                storage_path=storage_path,
                size_bytes=target_path.stat().st_size,
                created_at=utcnow_naive(),
                expires_at=None,
            )
        )


async def migrate_legacy_data(*, dry_run: bool = False) -> MigrationStats:
    stats = MigrationStats()
    async with AsyncSessionLocal() as session:
        admin = await ensure_admin(session)
        await migrate_uploads(session, admin, dry_run=dry_run, stats=stats)
        await migrate_results(session, admin, dry_run=dry_run, stats=stats)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy files into admin-owned multi-user storage.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without touching DB or files.")
    args = parser.parse_args()
    stats = asyncio.run(migrate_legacy_data(dry_run=args.dry_run))
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
