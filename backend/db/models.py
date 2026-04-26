"""SQLAlchemy 2.0 ORM models for the multi-user system.

Mirrors the schema described in docs/DATABASE_SCHEMA.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


# --------------------------------------------------------------------------
# Account & invitations
# --------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','vip','normal')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    vip_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_users_role", User.role)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_invite_codes_code", InviteCode.code)


class UserSettings(Base):
    """Reserved for future preferences. v1 unused."""
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferences_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


# --------------------------------------------------------------------------
# Files & batches
# --------------------------------------------------------------------------

class UploadBatch(Base):
    __tablename__ = "upload_batches"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('single','folder','multi_select')",
            name="ck_upload_batches_source_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_upload_batches_owner", UploadBatch.owner_user_id)


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(
            "file_type IN ('pdf','bibliography','markdown','docx','txt')",
            name="ck_files_file_type",
        ),
        UniqueConstraint("owner_user_id", "md5", name="uq_files_owner_md5"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    md5: Mapped[str] = mapped_column(String, nullable=False)
    batch_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("upload_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_files_owner", File.owner_user_id)
Index("idx_files_expires", File.expires_at)
Index("idx_files_batch", File.batch_id)


# --------------------------------------------------------------------------
# Jobs (filter / reading_* / compare / synthesis)
# --------------------------------------------------------------------------

class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis')",
            name="ck_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('pending','running','success','failed','canceled')",
            name="ck_jobs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    input_file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("files.id"), nullable=True)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_jobs_owner", Job.owner_user_id)
Index("idx_jobs_status", Job.status)
Index("idx_jobs_type", Job.job_type)
Index("idx_jobs_expires", Job.expires_at)


# --------------------------------------------------------------------------
# Bibliography entries (the hub)
# --------------------------------------------------------------------------

class BibEntry(Base):
    __tablename__ = "bib_entries"
    __table_args__ = (
        CheckConstraint(
            "source_db IN ('wos','cnki','scopus','manual','pdf_extracted',"
            "'md_extracted','other')",
            name="ck_bib_source_db",
        ),
        CheckConstraint(
            "reading_status IN ('none','has_pdf','reading','read')",
            name="ck_bib_reading_status",
        ),
        CheckConstraint(
            "metadata_completeness IN ('full','partial','minimal')",
            name="ck_bib_metadata_completeness",
        ),
        UniqueConstraint("owner_user_id", "dedup_key", name="uq_bib_dedup"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Bibliographic metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    keywords_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    venue_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    citation_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Provenance
    source_db: Mapped[str] = mapped_column(String, nullable=False)
    source_filter_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("jobs.id"), nullable=True
    )

    # Linked physical file (PDF or MD)
    source_file_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )

    # User annotations
    user_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    user_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # State
    reading_status: Mapped[str] = mapped_column(
        String, nullable=False, default="none", server_default="none"
    )
    metadata_completeness: Mapped[str] = mapped_column(
        String, nullable=False, default="partial", server_default="partial"
    )

    # Dedup
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_bib_owner", BibEntry.owner_user_id)
Index("idx_bib_status", BibEntry.reading_status)
Index("idx_bib_doi", BibEntry.doi)
Index("idx_bib_expires", BibEntry.expires_at)


# --------------------------------------------------------------------------
# Many-to-many associations
# --------------------------------------------------------------------------

class BibFilterLink(Base):
    """Records that a bib_entry was scored by a filter job."""
    __tablename__ = "bib_filter_links"
    __table_args__ = (
        UniqueConstraint("bib_entry_id", "filter_job_id", name="uq_bib_filter"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False
    )
    filter_job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    passed: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_bfl_bib", BibFilterLink.bib_entry_id)
Index("idx_bfl_filter", BibFilterLink.filter_job_id)


class JobBibEntry(Base):
    """Associates a job (reading/compare/synthesis) with one or more bib entries."""
    __tablename__ = "job_bib_entries"
    __table_args__ = (
        CheckConstraint(
            "role IN ('target','compare_member','synthesis_member')",
            name="ck_jbe_role",
        ),
        UniqueConstraint("job_id", "bib_entry_id", "role", name="uq_jbe_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


Index("idx_jbe_job", JobBibEntry.job_id)
Index("idx_jbe_bib", JobBibEntry.bib_entry_id)


# --------------------------------------------------------------------------
# Artifacts (job outputs)
# --------------------------------------------------------------------------

class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('reading_step','reading_final','reading_extract',"
            "'filter_excel','compare_excel','compare_md','synthesis_md')",
            name="ck_artifacts_artifact_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_artifacts_job", Artifact.job_id)
Index("idx_artifacts_owner", Artifact.owner_user_id)
Index("idx_artifacts_expires", Artifact.expires_at)
