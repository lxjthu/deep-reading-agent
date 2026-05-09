"""User data export/import service (.dra format).

Implements the design from:
docs/superpowers/specs/2026-05-06-user-data-export-import-design.md
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from cleanup import compute_expires_at_for_role, utcnow_naive
from db.models import (
    Artifact,
    BibEntry,
    BibFilterLink,
    BibReference,
    BibReferenceCitation,
    DimensionItem,
    DimensionSet,
    File,
    Job,
    JobBibEntry,
    PromptTemplate,
    ReadingItem,
    UploadBatch,
    User,
)
from cleanup import get_results_root
from upload_storage import get_upload_root, resolve_storage_path

FORMAT_VERSION = 1
SUPPORTED_FORMAT_VERSIONS = {1}
CURRENT_SCHEMA_VERSION = "007"

# FK forward order for export / import
EXPORT_TABLE_ORDER = [
    UploadBatch,
    File,
    PromptTemplate,
    DimensionSet,
    DimensionItem,
    BibEntry,
    Job,
    BibFilterLink,
    JobBibEntry,
    ReadingItem,
    Artifact,
    BibReference,
    BibReferenceCitation,
]

# FK reverse order for clear
IMPORT_CLEAR_ORDER = [
    BibReferenceCitation,
    BibReference,
    ReadingItem,
    Artifact,
    JobBibEntry,
    BibFilterLink,
    Job,
    BibEntry,
    DimensionItem,
    DimensionSet,
    File,
    UploadBatch,
    PromptTemplate,
]


def _model_name(model: type) -> str:
    return model.__tablename__


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _deserialize_value(value: Any, target_type: type) -> Any:
    if target_type is datetime and isinstance(value, str):
        # Handle both with and without timezone
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    return value


def _get_columns(model: type) -> list[str]:
    return [c.name for c in model.__table__.columns]


def _get_pk_column(model: type) -> str:
    pks = [c.name for c in model.__table__.columns if c.primary_key]
    return pks[0]


def _is_autoincrement_pk(model: type) -> bool:
    pk = _get_pk_column(model)
    col = model.__table__.columns[pk]
    return getattr(col, "autoincrement", False) is True


def _get_column_type(model: type, col_name: str) -> type:
    return model.__table__.columns[col_name].type.python_type


async def _query_user_records(db: AsyncSession, model: type, user_id: int) -> list[Any]:
    """Query all records for a user."""
    if model is PromptTemplate:
        result = await db.execute(
            select(model).where(
                model.owner_user_id == user_id,
                model.scope == "user",
            )
        )
    elif model is BibFilterLink:
        result = await db.execute(
            select(model)
            .join(Job, model.filter_job_id == Job.id)
            .where(Job.owner_user_id == user_id)
        )
    elif model is JobBibEntry:
        result = await db.execute(
            select(model)
            .join(Job, model.job_id == Job.id)
            .where(Job.owner_user_id == user_id)
        )
    elif model is DimensionItem:
        user_set_ids = select(DimensionSet.id).where(
            DimensionSet.owner_user_id == user_id
        )
        result = await db.execute(
            select(model).where(model.set_id.in_(user_set_ids))
        )
    else:
        result = await db.execute(select(model).where(model.owner_user_id == user_id))
    return result.scalars().all()


async def _serialize_table(db: AsyncSession, model: type, user_id: int) -> tuple[list[dict], list[str]]:
    """Serialize one table's user data to dict list + missing_files list."""
    records = await _query_user_records(db, model, user_id)
    columns = _get_columns(model)
    data: list[dict] = []
    missing_files: list[str] = []

    for record in records:
        row: dict[str, Any] = {}
        for col in columns:
            value = getattr(record, col)
            row[col] = _serialize_value(value)

        # Check physical files for File and Artifact
        if model is File:
            storage_path = getattr(record, "storage_path", None)
            if storage_path:
                physical = resolve_storage_path(storage_path)
                if not physical.exists():
                    row["_file_missing"] = True
                    missing_files.append(str(storage_path))

        if model is Artifact:
            storage_path = getattr(record, "storage_path", None)
            if storage_path:
                physical = get_results_root() / storage_path
                if not physical.exists():
                    row["_file_missing"] = True
                    missing_files.append(str(storage_path))

        data.append(row)

    return data, missing_files


async def export_user_data(db: AsyncSession, user: User) -> Path:
    """Build .dra export package, return path to temporary zip file."""
    timestamp = utcnow_naive().strftime("%Y%m%d_%H%M%S")
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"export_{user.id}_{timestamp}_"))
    data_dir = tmp_dir / "data"
    files_dir = tmp_dir / "files"
    artifacts_dir = tmp_dir / "artifacts"
    data_dir.mkdir()
    files_dir.mkdir()
    artifacts_dir.mkdir()

    stats: dict[str, int] = {}
    all_missing_files: list[str] = []
    errors: list[str] = []

    # Serialize tables
    for model in EXPORT_TABLE_ORDER:
        table_name = _model_name(model)
        try:
            records, missing = await _serialize_table(db, model, user.id)
            stats[table_name] = len(records)
            all_missing_files.extend(missing)

            json_path = data_dir / f"{table_name}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            errors.append(f"{table_name}: {exc}")
            stats[table_name] = 0

    # Copy physical files
    upload_root = get_upload_root()
    results_root = get_results_root()

    # Files
    file_records = await _query_user_records(db, File, user.id)
    for record in file_records:
        storage_path = record.storage_path
        if not storage_path:
            continue
        src = resolve_storage_path(storage_path)
        if src.exists():
            ext = Path(record.original_name).suffix if record.original_name else ".bin"
            dst = files_dir / f"{record.id}{ext}"
            try:
                shutil.copy2(src, dst)
            except Exception as exc:
                errors.append(f"copy file {record.id}: {exc}")

    # Artifacts
    artifact_records = await _query_user_records(db, Artifact, user.id)
    for record in artifact_records:
        storage_path = record.storage_path
        if not storage_path:
            continue
        src = results_root / storage_path
        if src.exists():
            job_dir = artifacts_dir / record.job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            dst = job_dir / record.filename
            try:
                shutil.copy2(src, dst)
            except Exception as exc:
                errors.append(f"copy artifact {record.id}: {exc}")

    # Write manifest
    manifest = {
        "format_version": FORMAT_VERSION,
        "exported_at": utcnow_naive().isoformat(),
        "source_host": os.getenv("HOST", "unknown"),
        "schema_version": CURRENT_SCHEMA_VERSION,
        "user": {
            "username": user.username,
            "role": user.role,
            "email": user.email,
        },
        "stats": stats,
        "missing_files": all_missing_files,
        "errors": errors,
    }
    with open(tmp_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # Zip it up
    zip_path = Path(tempfile.mktemp(suffix=".dra"))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(tmp_dir):
            for filename in files:
                file_path = Path(root) / filename
                arcname = str(file_path.relative_to(tmp_dir))
                zf.write(file_path, arcname)

    # Clean up temp dir
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return zip_path


async def _clear_user_data(db: AsyncSession, user_id: int) -> dict[str, int]:
    """Clear the importing user's data in FK reverse order.

    Only deletes records belonging to user_id, leaving other users' data intact.
    Junction tables without owner_user_id are filtered via subquery on Job.
    Returns deletion counts.
    """
    from sqlalchemy import exists

    counts: dict[str, int] = {}
    user_job_subq = select(Job.id).where(Job.owner_user_id == user_id)
    user_set_subq = select(DimensionSet.id).where(DimensionSet.owner_user_id == user_id)

    for model in IMPORT_CLEAR_ORDER:
        table_name = _model_name(model)
        if hasattr(model, "owner_user_id"):
            result = await db.execute(
                delete(model).where(model.owner_user_id == user_id)
            )
        elif model is DimensionItem:
            result = await db.execute(
                delete(DimensionItem).where(
                    DimensionItem.set_id.in_(user_set_subq)
                )
            )
        elif model is JobBibEntry:
            result = await db.execute(
                delete(JobBibEntry).where(
                    JobBibEntry.job_id.in_(user_job_subq)
                )
            )
        elif model is BibFilterLink:
            result = await db.execute(
                delete(BibFilterLink).where(
                    BibFilterLink.filter_job_id.in_(user_job_subq)
                )
            )
        else:
            result = await db.execute(delete(model))
        counts[table_name] = result.rowcount or 0
    return counts


async def _pre_delete_conflicts(
    db: AsyncSession,
    model: type,
    records: list[dict],
    pk_col: str,
    auto_pk: bool,
) -> None:
    """Delete existing DB rows that would collide with export data.

    Three strategies, applied in order:
    1. Non-auto PK tables: DELETE WHERE pk IN (export PKs)
    2. Tables with UniqueConstraint: DELETE by unique column combos
    3. Auto-PK tables: DELETE by FK column values (child rows whose
       parent was already replaced in step 1)
    """
    from sqlalchemy import UniqueConstraint

    # 1) PK-based delete for non-auto tables
    if not auto_pk:
        old_pks = [row[pk_col] for row in records if pk_col in row]
        if old_pks:
            await db.execute(delete(model).where(getattr(model, pk_col).in_(old_pks)))

    # 2) UniqueConstraint-based delete (junction tables etc.)
    for constraint in model.__table__.constraints:
        if not isinstance(constraint, UniqueConstraint):
            continue
        uq_cols = [c.name for c in constraint.columns]
        if sorted(uq_cols) == [pk_col]:
            continue
        conditions = []
        for row in records:
            if all(col in row for col in uq_cols):
                cond = and_(*[getattr(model, col) == row[col] for col in uq_cols])
                conditions.append(cond)
        if conditions:
            await db.execute(delete(model).where(or_(*conditions)))

    # 3) FK-based delete for auto-PK tables (e.g. Artifact)
    #    When parent records (jobs, bib_entries…) were deleted in step 1,
    #    their child rows in auto-PK tables still linger because SQLite
    #    doesn't enforce FK CASCADE.  Delete by FK column values.
    if auto_pk:
        for col in model.__table__.columns:
            if col.name == "owner_user_id" or col.name == pk_col:
                continue
            if not col.foreign_keys:
                continue
            fk_vals = list({
                row[col.name]
                for row in records
                if col.name in row and row[col.name] is not None
            })
            if fk_vals:
                await db.execute(
                    delete(model).where(getattr(model, col.name).in_(fk_vals))
                )


async def _deserialize_table(
    db: AsyncSession,
    model: type,
    records: list[dict],
    user_id: int,
    role: str,
    id_map: dict[tuple[str, int], int] | None = None,
) -> int:
    """Deserialize and insert records for one table. Returns inserted count."""
    if not records:
        return 0

    columns = _get_columns(model)
    pk_col = _get_pk_column(model)
    auto_pk = _is_autoincrement_pk(model)
    inserted = 0
    track_ids = id_map is not None and auto_pk

    await _pre_delete_conflicts(db, model, records, pk_col, auto_pk)

    new_expires_at = compute_expires_at_for_role(role)
    table_name = _model_name(model)
    created_objects: list[tuple[Any, Any]] = []

    for row in records:
        kwargs: dict[str, Any] = {}
        for col in columns:
            if col not in row:
                continue

            if col == pk_col and auto_pk:
                continue

            value = row[col]

            if col == "owner_user_id":
                kwargs[col] = user_id
                continue

            if col == "expires_at":
                kwargs[col] = new_expires_at
                continue

            if col == "set_id" and id_map and model is DimensionItem:
                new_set_id = id_map.get(("dimension_sets", value))
                if new_set_id is not None:
                    kwargs[col] = new_set_id
                    continue

            try:
                col_type = _get_column_type(model, col)
                if col_type is datetime and isinstance(value, str):
                    kwargs[col] = _deserialize_value(value, datetime)
                    continue
            except Exception:
                pass

            kwargs[col] = value

        try:
            obj = model(**kwargs)
            db.add(obj)
            inserted += 1
            if track_ids:
                created_objects.append((row.get(pk_col), obj))
        except Exception:
            continue

    if created_objects:
        await db.flush()
        for old_pk, obj in created_objects:
            if old_pk is not None and id_map is not None:
                id_map[(table_name, old_pk)] = obj.id

    return inserted


async def import_user_data(db: AsyncSession, user: User, dra_path: Path) -> dict[str, Any]:
    """Parse .dra package and import user data. Returns import stats."""
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"import_{user.id}_"))
    logger.info("[import] Starting import for user %s, temp dir: %s", user.id, tmp_dir)

    try:
        # Extract zip
        logger.info("[import] Extracting zip...")
        with zipfile.ZipFile(dra_path, "r") as zf:
            zf.extractall(tmp_dir)
        logger.info("[import] Zip extracted successfully")

        # Read manifest
        manifest_path = tmp_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("无效的导出包：缺少 manifest.json")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        format_version = manifest.get("format_version")
        if format_version not in SUPPORTED_FORMAT_VERSIONS:
            raise ValueError(f"导出包版本不兼容：{format_version}")

        data_dir = tmp_dir / "data"
        files_dir = tmp_dir / "files"
        artifacts_dir = tmp_dir / "artifacts"

        # Clear existing data
        logger.info("[import] Clearing existing user data...")
        uid = user.id
        urole = user.role
        clear_counts = await _clear_user_data(db, uid)
        await db.flush()
        logger.info("[import] Cleared data: %s", clear_counts)

        # Import tables in order
        import_counts: dict[str, int] = {}
        id_map: dict[tuple[str, int], int] = {}
        for model in EXPORT_TABLE_ORDER:
            table_name = _model_name(model)
            json_path = data_dir / f"{table_name}.json"
            if not json_path.exists():
                import_counts[table_name] = 0
                continue

            with open(json_path, "r", encoding="utf-8") as f:
                records = json.load(f)

            logger.info("[import] Importing table %s, %d records...", table_name, len(records))
            count = await _deserialize_table(db, model, records, uid, urole, id_map)
            await db.flush()
            import_counts[table_name] = count
            logger.info("[import] Table %s imported: %d records", table_name, count)

        # Commit all data changes in one transaction
        logger.info("[import] Committing transaction...")
        await db.commit()
        logger.info("[import] Transaction committed")

        # Prepare file restoration info BEFORE closing transaction context
        # (collect all needed info while session is still valid)
        files_to_restore: list[tuple[Path, Path]] = []
        artifacts_to_restore: list[tuple[Path, Path]] = []

        upload_root = get_upload_root()
        results_root = get_results_root()

        # Collect file restoration info
        if files_dir.exists():
            for src_path in files_dir.iterdir():
                if not src_path.is_file():
                    continue
                file_id = src_path.stem
                result = await db.execute(select(File).where(File.id == file_id))
                record = result.scalars().first()
                if record is None:
                    logger.warning("[import] File record not found for id=%s", file_id)
                    continue
                if getattr(record, "_file_missing", False):
                    logger.warning("[import] File marked as missing: id=%s", file_id)
                    continue
                dst = resolve_storage_path(record.storage_path)
                files_to_restore.append((src_path, dst))

        # Collect artifact restoration info
        if artifacts_dir.exists():
            for job_dir in artifacts_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                job_id = job_dir.name
                for src_path in job_dir.iterdir():
                    if not src_path.is_file():
                        continue
                    filename = src_path.name
                    result = await db.execute(
                        select(Artifact).where(
                            Artifact.job_id == job_id,
                            Artifact.filename == filename,
                        )
                    )
                    record = result.scalars().first()
                    if record is None:
                        logger.warning("[import] Artifact record not found: job_id=%s, filename=%s", job_id, filename)
                        continue
                    if getattr(record, "_file_missing", False):
                        logger.warning("[import] Artifact marked as missing: job_id=%s, filename=%s", job_id, filename)
                        continue
                    dst = results_root / record.storage_path
                    artifacts_to_restore.append((src_path, dst))

        # Restore physical files (outside transaction, best-effort)
        files_restored = 0
        files_missing = 0

        for src_path, dst_path in files_to_restore:
            try:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                files_restored += 1
                logger.info("[import] Restored file: %s -> %s", src_path, dst_path)
            except Exception as exc:
                files_missing += 1
                logger.error("[import] Failed to restore file %s: %s", src_path, exc)

        for src_path, dst_path in artifacts_to_restore:
            try:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                files_restored += 1
                logger.info("[import] Restored artifact: %s -> %s", src_path, dst_path)
            except Exception as exc:
                files_missing += 1
                logger.error("[import] Failed to restore artifact %s: %s", src_path, exc)

        logger.info("[import] Import completed. restored=%d, missing=%d", files_restored, files_missing)
        return {
            "cleared": clear_counts,
            "imported": import_counts,
            "files_restored": files_restored,
            "files_missing": files_missing,
            "manifest": manifest,
        }

    except Exception as exc:
        logger.error("[import] Import failed: %s", exc, exc_info=True)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info("[import] Cleaned up temp dir: %s", tmp_dir)
