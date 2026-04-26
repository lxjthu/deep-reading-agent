"""initial schema (multi-user system)

Revision ID: 001_initial
Revises:
Create Date: 2026-04-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- users ----------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(), nullable=False, unique=True),
        sa.Column("email", sa.String(), nullable=True, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("vip_expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('admin','vip','normal')", name="ck_users_role"),
    )
    op.create_index("idx_users_role", "users", ["role"])

    # ---------------- invite_codes ----------------
    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("idx_invite_codes_code", "invite_codes", ["code"])

    # ---------------- user_settings ----------------
    op.create_table(
        "user_settings",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("preferences_json", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )

    # ---------------- upload_batches ----------------
    op.create_table(
        "upload_batches",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "source_type IN ('single','folder','multi_select')",
            name="ck_upload_batches_source_type",
        ),
    )
    op.create_index("idx_upload_batches_owner", "upload_batches", ["owner_user_id"])

    # ---------------- files ----------------
    op.create_table(
        "files",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_name", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("md5", sa.String(), nullable=False),
        sa.Column("batch_id", sa.String(), sa.ForeignKey("upload_batches.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "file_type IN ('pdf','bibliography','markdown','docx','txt')",
            name="ck_files_file_type",
        ),
        sa.UniqueConstraint("owner_user_id", "md5", name="uq_files_owner_md5"),
    )
    op.create_index("idx_files_owner", "files", ["owner_user_id"])
    op.create_index("idx_files_expires", "files", ["expires_at"])
    op.create_index("idx_files_batch", "files", ["batch_id"])

    # ---------------- jobs ----------------
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("job_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("input_file_id", sa.String(), sa.ForeignKey("files.id"), nullable=True),
        sa.Column("params_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_stage", sa.String(), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("batch_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis')",
            name="ck_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','success','failed','canceled')",
            name="ck_jobs_status",
        ),
    )
    op.create_index("idx_jobs_owner", "jobs", ["owner_user_id"])
    op.create_index("idx_jobs_status", "jobs", ["status"])
    op.create_index("idx_jobs_type", "jobs", ["job_type"])
    op.create_index("idx_jobs_expires", "jobs", ["expires_at"])

    # ---------------- bib_entries ----------------
    op.create_table(
        "bib_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(), nullable=True),
        sa.Column("journal", sa.String(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("keywords_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("venue_type", sa.String(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("source_db", sa.String(), nullable=False),
        sa.Column(
            "source_filter_job_id",
            sa.String(),
            sa.ForeignKey("jobs.id"),
            nullable=True,
        ),
        sa.Column(
            "source_file_id",
            sa.String(),
            sa.ForeignKey("files.id"),
            nullable=True,
        ),
        sa.Column("user_tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("user_note", sa.Text(), nullable=True),
        sa.Column("is_pinned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reading_status", sa.String(), nullable=False, server_default="none"),
        sa.Column(
            "metadata_completeness",
            sa.String(),
            nullable=False,
            server_default="partial",
        ),
        sa.Column("dedup_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "source_db IN ('wos','cnki','scopus','manual','pdf_extracted',"
            "'md_extracted','other')",
            name="ck_bib_source_db",
        ),
        sa.CheckConstraint(
            "reading_status IN ('none','has_pdf','reading','read')",
            name="ck_bib_reading_status",
        ),
        sa.CheckConstraint(
            "metadata_completeness IN ('full','partial','minimal')",
            name="ck_bib_metadata_completeness",
        ),
        sa.UniqueConstraint("owner_user_id", "dedup_key", name="uq_bib_dedup"),
    )
    op.create_index("idx_bib_owner", "bib_entries", ["owner_user_id"])
    op.create_index("idx_bib_status", "bib_entries", ["reading_status"])
    op.create_index("idx_bib_doi", "bib_entries", ["doi"])
    op.create_index("idx_bib_expires", "bib_entries", ["expires_at"])

    # ---------------- bib_filter_links ----------------
    op.create_table(
        "bib_filter_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "bib_entry_id",
            sa.String(),
            sa.ForeignKey("bib_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "filter_job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint("bib_entry_id", "filter_job_id", name="uq_bib_filter"),
    )
    op.create_index("idx_bfl_bib", "bib_filter_links", ["bib_entry_id"])
    op.create_index("idx_bfl_filter", "bib_filter_links", ["filter_job_id"])

    # ---------------- job_bib_entries ----------------
    op.create_table(
        "job_bib_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bib_entry_id",
            sa.String(),
            sa.ForeignKey("bib_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "role IN ('target','compare_member','synthesis_member')",
            name="ck_jbe_role",
        ),
        sa.UniqueConstraint("job_id", "bib_entry_id", "role", name="uq_jbe_unique"),
    )
    op.create_index("idx_jbe_job", "job_bib_entries", ["job_id"])
    op.create_index("idx_jbe_bib", "job_bib_entries", ["bib_entry_id"])

    # ---------------- artifacts ----------------
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "artifact_type IN ('reading_step','reading_final','reading_extract',"
            "'filter_excel','compare_excel','compare_md','synthesis_md')",
            name="ck_artifacts_artifact_type",
        ),
    )
    op.create_index("idx_artifacts_job", "artifacts", ["job_id"])
    op.create_index("idx_artifacts_owner", "artifacts", ["owner_user_id"])
    op.create_index("idx_artifacts_expires", "artifacts", ["expires_at"])


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("job_bib_entries")
    op.drop_table("bib_filter_links")
    op.drop_table("bib_entries")
    op.drop_table("jobs")
    op.drop_table("files")
    op.drop_table("upload_batches")
    op.drop_table("user_settings")
    op.drop_table("invite_codes")
    op.drop_table("users")
