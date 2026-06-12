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
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from cleanup import compute_expires_at_for_role, utcnow_naive
from db.models import (
    Artifact,
    AgentActionProposal,
    AgentMessage,
    AgentSession,
    BibAttachment,
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
    Annotation,
    PromptTemplate,
    ReadingItem,
    ReadingItemEdit,
    ReadingSourceEvidence,
    RefFormatPreset,
    UploadBatch,
    User,
)
from result_storage import get_results_root, resolve_result_path
from upload_storage import build_storage_path, get_upload_root, resolve_storage_path

FORMAT_VERSION = 1
SUPPORTED_FORMAT_VERSIONS = {1}
CURRENT_SCHEMA_VERSION = "026"
IMPORT_MODE_APPEND = "merge_append"
IMPORT_MODE_REPLACE = "merge_replace"
SUPPORTED_IMPORT_MODES = {IMPORT_MODE_APPEND, IMPORT_MODE_REPLACE}

# Deliberately excluded from .dra export/import:
# - user_feedback
# - feedback_events
# - admin_audit_logs
#
# These tables are administrator-facing product operations records, not user
# research workspace data. Feedback is retained for admin follow-up even when
# normal-user workspace data expires; if privacy deletion is needed later, add
# a dedicated anonymization/deletion flow instead of coupling it to .dra.

# FK forward order for export / import
# CRITICAL: Job must come before BibEntry because bib_entries.source_filter_job_id -> jobs.id
EXPORT_TABLE_ORDER = [
    UploadBatch,
    File,
    PromptTemplate,
    DimensionSet,
    DimensionItem,
    RefFormatPreset,
    Job,  # Moved before BibEntry to satisfy FK constraint
    BibEntry,
    BibAttachment,
    BibFilterLink,
    JobBibEntry,
    ReadingItem,
    ReadingSourceEvidence,
    ReadingItemEdit,
    Annotation,
    AgentSession,
    AgentMessage,
    AgentActionProposal,
    Artifact,
    CardNote,
    BibReference,
    BibReferenceCitation,
]

# FK reverse order for clear
IMPORT_CLEAR_ORDER = [
    BibReferenceCitation,
    BibReference,
    CardNote,
    Annotation,
    ReadingItemEdit,
    ReadingSourceEvidence,
    ReadingItem,
    Artifact,
    AgentActionProposal,
    AgentMessage,
    AgentSession,
    JobBibEntry,
    BibFilterLink,
    BibAttachment,
    Job,
    BibEntry,
    RefFormatPreset,
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

        if model is CardNote:
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
    card_notes_dir = tmp_dir / "card_notes"
    data_dir.mkdir()
    files_dir.mkdir()
    artifacts_dir.mkdir()
    card_notes_dir.mkdir()

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

    # Card note mirrors
    card_records = await _query_user_records(db, CardNote, user.id)
    for record in card_records:
        storage_path = record.storage_path
        if not storage_path:
            continue
        src = results_root / storage_path
        if src.exists():
            dst = card_notes_dir / f"{record.id}.md"
            try:
                shutil.copy2(src, dst)
            except Exception as exc:
                errors.append(f"copy card note {record.id}: {exc}")

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


def _new_uuid_str() -> str:
    return str(uuid.uuid4())


def _normalize_schema_version(value: Any) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip()
    if text.startswith("0"):
        return text
    if text.startswith("revision:"):
        return text.split(":", 1)[1].strip()
    if text.startswith("0") or text.isdigit():
        return text
    return text


def _ensure_supported_import_mode(mode: str) -> str:
    normalized = (mode or IMPORT_MODE_APPEND).strip()
    if normalized not in SUPPORTED_IMPORT_MODES:
        raise ValueError(f"不支持的导入模式：{normalized}")
    return normalized


def _empty_table_stats() -> dict[str, int]:
    return {
        "created": 0,
        "reused": 0,
        "replaced": 0,
        "skipped": 0,
        "errors": 0,
    }


def _record_table_stat(table_stats: dict[str, dict[str, int]], table_name: str, key: str) -> None:
    table_stats.setdefault(table_name, _empty_table_stats())[key] += 1


def _safe_extract_zip(dra_path: Path, tmp_dir: Path) -> None:
    with zipfile.ZipFile(dra_path, "r") as zf:
        for member in zf.infolist():
            target_path = (tmp_dir / member.filename).resolve()
            if not str(target_path).startswith(str(tmp_dir.resolve())):
                raise ValueError("无效的导出包：包含不安全的压缩路径。")
        zf.extractall(tmp_dir)


def _load_json_records(json_path: Path) -> list[dict[str, Any]]:
    if not json_path.exists():
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    raise ValueError(f"无效的 JSON 数据：{json_path.name}")


def _remember_id_map(
    id_map: dict[tuple[str, Any], Any],
    table_name: str,
    old_id: Any,
    new_id: Any,
) -> None:
    if old_id is not None and new_id is not None:
        id_map[(table_name, old_id)] = new_id


def _mapped_value(
    id_map: dict[tuple[str, Any], Any],
    table_name: str,
    old_id: Any,
) -> Any:
    return id_map.get((table_name, old_id), old_id)


FK_REMAP_FIELDS: dict[str, dict[str, str]] = {
    "files": {"batch_id": "upload_batches"},
    "jobs": {"input_file_id": "files"},
    "bib_entries": {
        "source_filter_job_id": "jobs",
        "source_file_id": "files",
        "markdown_source_file_id": "files",
    },
    "dimension_items": {"set_id": "dimension_sets"},
    "bib_filter_links": {
        "bib_entry_id": "bib_entries",
        "filter_job_id": "jobs",
    },
    "job_bib_entries": {
        "job_id": "jobs",
        "bib_entry_id": "bib_entries",
    },
    "reading_items": {
        "bib_entry_id": "bib_entries",
        "job_id": "jobs",
    },
    "reading_source_evidence": {
        "bib_entry_id": "bib_entries",
        "job_id": "jobs",
        "reading_item_id": "reading_items",
        "source_file_id": "files",
    },
    "reading_item_edits": {"reading_item_id": "reading_items"},
    "agent_messages": {"session_id": "agent_sessions"},
    "agent_action_proposals": {"session_id": "agent_sessions"},
    "artifacts": {"job_id": "jobs"},
    "card_notes": {
        "source_bib_entry_id": "bib_entries",
        "source_markdown_file_id": "files",
        "source_translation_artifact_id": "artifacts",
    },
    "bib_references": {
        "source_bib_entry_id": "bib_entries",
        "source_job_id": "jobs",
        "matched_bib_entry_id": "bib_entries",
    },
    "bib_reference_citations": {
        "source_bib_entry_id": "bib_entries",
        "bib_reference_id": "bib_references",
        "source_job_id": "jobs",
    },
    "annotations": {"bib_entry_id": "bib_entries"},
    "bib_attachments": {
        "bib_entry_id": "bib_entries",
        "file_id": "files",
    },
}


def _rewrite_file_storage_path(user_id: int, file_id: str, original_name: str | None) -> str:
    ext = Path(original_name or "file.bin").suffix or ".bin"
    _absolute_path, storage_path = build_storage_path(user_id, file_id, ext)
    return storage_path


def _rewrite_artifact_storage_path(user_id: int, job_id: str | None, filename: str | None) -> str:
    safe_filename = filename or f"artifact-{_new_uuid_str()}.bin"
    safe_job_id = job_id or _new_uuid_str()
    return Path(str(user_id)) / safe_job_id / safe_filename
    # return relative path as posix string


def _artifact_storage_path_as_posix(user_id: int, job_id: str | None, filename: str | None) -> str:
    return _rewrite_artifact_storage_path(user_id, job_id, filename).as_posix()


def _rewrite_card_note_storage_path(user_id: int, card_id: str) -> str:
    return (Path(str(user_id)) / "notes" / "cards" / f"{card_id}.md").as_posix()


def _update_existing_record(
    obj: Any,
    kwargs: dict[str, Any],
    *,
    exclude: set[str] | None = None,
) -> None:
    excluded = exclude or set()
    for key, value in kwargs.items():
        if key in excluded:
            continue
        setattr(obj, key, value)


def _build_row_kwargs(
    model: type,
    row: dict[str, Any],
    *,
    user_id: int,
    role: str,
    id_map: dict[tuple[str, Any], Any],
) -> dict[str, Any]:
    columns = _get_columns(model)
    pk_col = _get_pk_column(model)
    auto_pk = _is_autoincrement_pk(model)
    table_name = _model_name(model)
    expires_at = compute_expires_at_for_role(role)
    kwargs: dict[str, Any] = {}

    for col in columns:
        if col not in row:
            continue

        if auto_pk and col == pk_col:
            continue

        value = row[col]

        if col == "owner_user_id":
            kwargs[col] = user_id
            continue

        if col == "updated_by_user_id":
            kwargs[col] = user_id
            continue

        if col == "scope" and model is PromptTemplate:
            kwargs[col] = "user"
            continue

        if col == "expires_at":
            kwargs[col] = expires_at
            continue

        target_table = FK_REMAP_FIELDS.get(table_name, {}).get(col)
        if target_table and value is not None:
            value = _mapped_value(id_map, target_table, value)

        if model is Annotation and col == "source_id":
            source_type = row.get("source_type")
            if source_type in {"compare_card", "ai_summary"}:
                try:
                    source_value = int(value)
                except (TypeError, ValueError):
                    source_value = None
                if source_value is not None:
                    value = str(_mapped_value(id_map, "reading_items", source_value))

        try:
            col_type = _get_column_type(model, col)
            if col_type is datetime and isinstance(value, str):
                value = _deserialize_value(value, datetime)
        except Exception:
            pass

        kwargs[col] = value

    return kwargs


async def _select_one(
    db: AsyncSession,
    statement: Any,
) -> Any | None:
    result = await db.execute(statement)
    return result.scalars().first()


async def _find_existing_record(
    db: AsyncSession,
    model: type,
    kwargs: dict[str, Any],
    *,
    user_id: int,
    old_pk: Any,
) -> Any | None:
    if model is File and kwargs.get("md5"):
        return await _select_one(
            db,
            select(File).where(
                File.owner_user_id == user_id,
                File.md5 == kwargs["md5"],
            ),
        )

    if model is PromptTemplate:
        return await _select_one(
            db,
            select(PromptTemplate).where(
                PromptTemplate.owner_user_id == user_id,
                PromptTemplate.scope == "user",
                PromptTemplate.prompt_type == kwargs.get("prompt_type"),
                PromptTemplate.prompt_key == kwargs.get("prompt_key"),
            ),
        )

    if model is DimensionSet:
        return await _select_one(
            db,
            select(DimensionSet).where(
                DimensionSet.owner_user_id == user_id,
                DimensionSet.name == kwargs.get("name"),
            ),
        )

    if model is DimensionItem:
        return await _select_one(
            db,
            select(DimensionItem).where(
                DimensionItem.set_id == kwargs.get("set_id"),
                DimensionItem.dim_key == kwargs.get("dim_key"),
            ),
        )

    if model is RefFormatPreset:
        return await _select_one(
            db,
            select(RefFormatPreset).where(
                RefFormatPreset.owner_user_id == user_id,
                RefFormatPreset.name == kwargs.get("name"),
            ),
        )

    if model is BibEntry:
        dedup_key = kwargs.get("dedup_key")
        if dedup_key:
            return await _select_one(
                db,
                select(BibEntry).where(
                    BibEntry.owner_user_id == user_id,
                    BibEntry.dedup_key == dedup_key,
                ),
            )

    if model is BibFilterLink:
        return await _select_one(
            db,
            select(BibFilterLink).where(
                BibFilterLink.bib_entry_id == kwargs.get("bib_entry_id"),
                BibFilterLink.filter_job_id == kwargs.get("filter_job_id"),
            ),
        )

    if model is JobBibEntry:
        return await _select_one(
            db,
            select(JobBibEntry).where(
                JobBibEntry.job_id == kwargs.get("job_id"),
                JobBibEntry.bib_entry_id == kwargs.get("bib_entry_id"),
                JobBibEntry.role == kwargs.get("role"),
            ),
        )

    if model is ReadingItem:
        return await _select_one(
            db,
            select(ReadingItem).where(
                ReadingItem.job_id == kwargs.get("job_id"),
                ReadingItem.item_key == kwargs.get("item_key"),
            ),
        )

    if model is ReadingItemEdit:
        return await _select_one(
            db,
            select(ReadingItemEdit).where(
                ReadingItemEdit.reading_item_id == kwargs.get("reading_item_id"),
                ReadingItemEdit.owner_user_id == user_id,
            ),
        )

    if model is Artifact:
        return await _select_one(
            db,
            select(Artifact).where(
                Artifact.owner_user_id == user_id,
                Artifact.job_id == kwargs.get("job_id"),
                Artifact.artifact_type == kwargs.get("artifact_type"),
                Artifact.filename == kwargs.get("filename"),
            ),
        )

    if model is CardNote:
        return await _select_one(
            db,
            select(CardNote).where(
                CardNote.owner_user_id == user_id,
                CardNote.source_bib_entry_id == kwargs.get("source_bib_entry_id"),
                CardNote.source_version == kwargs.get("source_version"),
                CardNote.title == kwargs.get("title"),
            ),
        )

    if model is BibReference:
        if kwargs.get("dedup_key"):
            return await _select_one(
                db,
                select(BibReference).where(
                    BibReference.owner_user_id == user_id,
                    BibReference.source_bib_entry_id == kwargs.get("source_bib_entry_id"),
                    BibReference.dedup_key == kwargs.get("dedup_key"),
                ),
            )
        return await _select_one(
            db,
            select(BibReference).where(
                BibReference.owner_user_id == user_id,
                BibReference.source_bib_entry_id == kwargs.get("source_bib_entry_id"),
                BibReference.raw_text == kwargs.get("raw_text"),
            ),
        )

    if model is BibReferenceCitation:
        return await _select_one(
            db,
            select(BibReferenceCitation).where(
                BibReferenceCitation.owner_user_id == user_id,
                BibReferenceCitation.bib_reference_id == kwargs.get("bib_reference_id"),
                BibReferenceCitation.citation_index == kwargs.get("citation_index"),
                BibReferenceCitation.quote_text == kwargs.get("quote_text"),
            ),
        )

    if old_pk is not None:
        existing = await db.get(model, old_pk)
        if existing is not None and getattr(existing, "owner_user_id", user_id) == user_id:
            return existing

    return None


async def _apply_record_import(
    db: AsyncSession,
    model: type,
    row: dict[str, Any],
    *,
    user: User,
    mode: str,
    id_map: dict[tuple[str, Any], Any],
    table_stats: dict[str, dict[str, int]],
    restore_maps: dict[str, dict[str, str]],
) -> None:
    table_name = _model_name(model)
    pk_col = _get_pk_column(model)
    auto_pk = _is_autoincrement_pk(model)
    old_pk = row.get(pk_col)
    source_job_id = row.get("job_id")
    source_filename = row.get("filename")
    kwargs = _build_row_kwargs(model, row, user_id=user.id, role=user.role, id_map=id_map)

    if model is PromptTemplate:
        kwargs["scope"] = "user"

    # Use nested transaction (SAVEPOINT) to isolate flush failures.
    # This ensures a single record's FK violation doesn't corrupt the entire session.
    try:
        async with db.begin_nested():
            existing = await _find_existing_record(db, model, kwargs, user_id=user.id, old_pk=old_pk)

            if existing is not None:
                existing_pk = getattr(existing, pk_col)
                _remember_id_map(id_map, table_name, old_pk, existing_pk)

                if model is File:
                    restore_maps["files"][str(old_pk)] = existing.storage_path
                    if mode == IMPORT_MODE_REPLACE:
                        _update_existing_record(
                            existing,
                            {
                                "original_name": kwargs.get("original_name"),
                                "file_type": kwargs.get("file_type"),
                                "size_bytes": kwargs.get("size_bytes"),
                                "batch_id": kwargs.get("batch_id"),
                                "expires_at": kwargs.get("expires_at"),
                            },
                        )
                        _record_table_stat(table_stats, table_name, "replaced")
                    else:
                        _record_table_stat(table_stats, table_name, "reused")
                    await db.flush()
                    return

                if model in {PromptTemplate, DimensionSet, DimensionItem, RefFormatPreset, BibEntry, ReadingItem, ReadingItemEdit, Artifact, CardNote, BibReference, BibReferenceCitation, BibFilterLink, JobBibEntry}:
                    if mode == IMPORT_MODE_REPLACE:
                        exclude = {pk_col, "owner_user_id"}
                        if model is Artifact:
                            kwargs["storage_path"] = existing.storage_path or _artifact_storage_path_as_posix(
                                user.id,
                                kwargs.get("job_id"),
                                kwargs.get("filename"),
                            )
                        if model is CardNote:
                            kwargs["storage_path"] = existing.storage_path or _rewrite_card_note_storage_path(
                                user.id,
                                getattr(existing, "id"),
                            )
                        _update_existing_record(existing, kwargs, exclude=exclude)
                        _record_table_stat(table_stats, table_name, "replaced")
                    else:
                        _record_table_stat(table_stats, table_name, "reused")

                    if model is Artifact and source_job_id is not None and source_filename:
                        restore_maps["artifacts"][f"{source_job_id}::{source_filename}"] = existing.storage_path
                    if model is CardNote and old_pk is not None and existing.storage_path:
                        restore_maps["card_notes"][str(old_pk)] = existing.storage_path
                    await db.flush()
                    return

                if model in {UploadBatch, Job, AgentSession, AgentMessage, AgentActionProposal, Annotation}:
                    if mode == IMPORT_MODE_REPLACE:
                        _update_existing_record(existing, kwargs, exclude={pk_col, "owner_user_id"})
                        _record_table_stat(table_stats, table_name, "replaced")
                        await db.flush()
                    return

            if not auto_pk:
                target_pk = old_pk or _new_uuid_str()
                existing_by_pk = await db.get(model, target_pk) if target_pk is not None else None

                if existing_by_pk is not None and getattr(existing_by_pk, "owner_user_id", user.id) != user.id:
                    target_pk = _new_uuid_str()
                    existing_by_pk = None

                if existing_by_pk is not None:
                    target_pk = _new_uuid_str()

                kwargs[pk_col] = target_pk

                if model is File:
                    kwargs["storage_path"] = _rewrite_file_storage_path(user.id, target_pk, kwargs.get("original_name"))
                elif model is CardNote:
                    kwargs["storage_path"] = _rewrite_card_note_storage_path(user.id, target_pk)

                obj = model(**kwargs)
                db.add(obj)
                await db.flush()
                _remember_id_map(id_map, table_name, old_pk, getattr(obj, pk_col))
                _record_table_stat(table_stats, table_name, "created")

                if model is File and old_pk is not None:
                    restore_maps["files"][str(old_pk)] = obj.storage_path
                elif model is CardNote and old_pk is not None and obj.storage_path:
                    restore_maps["card_notes"][str(old_pk)] = obj.storage_path
                return

            if model is Artifact:
                kwargs["storage_path"] = _artifact_storage_path_as_posix(
                    user.id,
                    kwargs.get("job_id"),
                    kwargs.get("filename"),
                )

            obj = model(**kwargs)
            db.add(obj)
            await db.flush()
            _remember_id_map(id_map, table_name, old_pk, getattr(obj, pk_col))
            _record_table_stat(table_stats, table_name, "created")

            if model is Artifact and source_job_id is not None and source_filename:
                restore_maps["artifacts"][f"{source_job_id}::{source_filename}"] = obj.storage_path
            if model is CardNote and old_pk is not None and obj.storage_path:
                restore_maps["card_notes"][str(old_pk)] = obj.storage_path

    except Exception as exc:
        # Rollback to SAVEPOINT and log error; outer transaction continues
        logger.warning("[import] Skip %s record due to error: %s", table_name, exc, exc_info=True)
        _record_table_stat(table_stats, table_name, "errors")
        # Exception already rolled back the nested transaction, so we swallow it here


ProgressCallback = Callable[[str, int], None]


async def import_user_data(
    db: AsyncSession,
    user: User,
    dra_path: Path,
    progress_cb: ProgressCallback | None = None,
    *,
    mode: str = IMPORT_MODE_APPEND,
) -> dict[str, Any]:
    """Parse .dra package and import user data without clearing the whole workspace."""
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"import_{user.id}_"))
    logger.info("[import] Starting import for user %s, temp dir: %s", user.id, tmp_dir)

    try:
        mode = _ensure_supported_import_mode(mode)
        if progress_cb:
            progress_cb("正在解压导出包...", 5)
        _safe_extract_zip(dra_path, tmp_dir)

        manifest_path = tmp_dir / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("无效的导出包：缺少 manifest.json")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        format_version = manifest.get("format_version")
        if format_version not in SUPPORTED_FORMAT_VERSIONS:
            raise ValueError(f"导出包版本不兼容：{format_version}")

        compat_warnings: list[str] = []
        manifest_schema = _normalize_schema_version(manifest.get("schema_version"))
        normalized_from_legacy = manifest_schema not in {CURRENT_SCHEMA_VERSION, "unknown"}
        if normalized_from_legacy:
            compat_warnings.append(
                f"导出包 schema_version={manifest_schema}，已按当前版本兼容导入。"
            )

        data_dir = tmp_dir / "data"
        files_dir = tmp_dir / "files"
        artifacts_dir = tmp_dir / "artifacts"
        card_notes_dir = tmp_dir / "card_notes"

        bundle: dict[str, list[dict[str, Any]]] = {}
        for model in EXPORT_TABLE_ORDER:
            table_name = _model_name(model)
            json_path = data_dir / f"{table_name}.json"
            records = _load_json_records(json_path)
            if not json_path.exists():
                compat_warnings.append(f"{table_name}.json 缺失，按空表处理。")
            bundle[table_name] = records

        uid = user.id
        table_stats: dict[str, dict[str, int]] = {}
        import_counts: dict[str, int] = {}
        id_map: dict[tuple[str, Any], Any] = {}
        restore_maps: dict[str, dict[str, str]] = {
            "files": {},
            "artifacts": {},
            "card_notes": {},
        }

        total_tables = len(EXPORT_TABLE_ORDER)
        for index, model in enumerate(EXPORT_TABLE_ORDER):
            table_name = _model_name(model)
            records = bundle.get(table_name, [])
            table_stats.setdefault(table_name, _empty_table_stats())

            if progress_cb:
                progress = 18 + int((index / max(total_tables, 1)) * 54)
                progress_cb(
                    f"正在以{'覆盖' if mode == IMPORT_MODE_REPLACE else '追加'}模式导入 {table_name}（{len(records)} 条）...",
                    progress,
                )

            for row in records:
                await _apply_record_import(
                    db,
                    model,
                    row,
                    user=user,
                    mode=mode,
                    id_map=id_map,
                    table_stats=table_stats,
                    restore_maps=restore_maps,
                )

            stats = table_stats[table_name]
            import_counts[table_name] = stats["created"] + stats["reused"] + stats["replaced"]

        if progress_cb:
            progress_cb("正在提交数据库事务...", 78)
        await db.commit()

        files_restored = 0
        files_missing = 0

        if progress_cb:
            progress_cb("正在恢复源文件和产物...", 86)

        if files_dir.exists():
            for src_path in files_dir.iterdir():
                if not src_path.is_file():
                    continue
                storage_path = restore_maps["files"].get(src_path.stem)
                if not storage_path:
                    files_missing += 1
                    continue
                dst = resolve_storage_path(storage_path)
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dst)
                    files_restored += 1
                except Exception as exc:
                    logger.error("[import] Failed to restore file %s: %s", src_path, exc)
                    files_missing += 1

        if artifacts_dir.exists():
            for job_dir in artifacts_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                for src_path in job_dir.iterdir():
                    if not src_path.is_file():
                        continue
                    storage_path = restore_maps["artifacts"].get(f"{job_dir.name}::{src_path.name}")
                    if not storage_path:
                        files_missing += 1
                        continue
                    dst = resolve_result_path(storage_path)
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_path, dst)
                        files_restored += 1
                    except Exception as exc:
                        logger.error("[import] Failed to restore artifact %s: %s", src_path, exc)
                        files_missing += 1

        if card_notes_dir.exists():
            for src_path in card_notes_dir.iterdir():
                if not src_path.is_file():
                    continue
                storage_path = restore_maps["card_notes"].get(src_path.stem)
                if not storage_path:
                    files_missing += 1
                    continue
                dst = resolve_result_path(storage_path)
                try:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dst)
                    files_restored += 1
                except Exception as exc:
                    logger.error("[import] Failed to restore card note %s: %s", src_path, exc)
                    files_missing += 1

        if progress_cb:
            progress_cb("导入完成。", 100)

        return {
            "mode": mode,
            "cleared": {},
            "imported": import_counts,
            "table_stats": table_stats,
            "files_restored": files_restored,
            "files_missing": files_missing,
            "manifest": manifest,
            "compat": {
                "schema_version": manifest_schema,
                "normalized_from_legacy": normalized_from_legacy,
                "warnings": compat_warnings,
            },
        }

    except Exception as exc:
        await db.rollback()
        logger.error("[import] Import failed: %s", exc, exc_info=True)
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.info("[import] Cleaned up temp dir: %s", tmp_dir)
