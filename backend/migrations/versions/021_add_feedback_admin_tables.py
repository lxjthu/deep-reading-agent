"""add feedback and admin audit tables

Revision ID: 021_add_feedback_admin_tables
Revises: 020_add_markdown_card_notes
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_add_feedback_admin_tables"
down_revision: Union[str, None] = "020_add_markdown_card_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("feedback_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), server_default="open", nullable=False),
        sa.Column("priority", sa.String(), server_default="P3", nullable=False),
        sa.Column("route", sa.String(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("app_version", sa.String(), nullable=True),
        sa.Column("related_job_id", sa.String(), nullable=True),
        sa.Column("related_file_id", sa.String(), nullable=True),
        sa.Column("related_bib_entry_id", sa.String(), nullable=True),
        sa.Column("related_artifact_id", sa.Integer(), nullable=True),
        sa.Column("assigned_admin_id", sa.Integer(), nullable=True),
        sa.Column("public_reply", sa.Text(), nullable=True),
        sa.Column("internal_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint(
            "feedback_type IN ('bug','feature','question','data_issue','translation','reading_quality','other')",
            name="ck_user_feedback_type",
        ),
        sa.CheckConstraint(
            "status IN ('open','triaged','in_progress','resolved','closed','reopened')",
            name="ck_user_feedback_status",
        ),
        sa.CheckConstraint("priority IN ('P0','P1','P2','P3')", name="ck_user_feedback_priority"),
        sa.ForeignKeyConstraint(["assigned_admin_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_artifact_id"], ["artifacts.id"]),
        sa.ForeignKeyConstraint(["related_bib_entry_id"], ["bib_entries.id"]),
        sa.ForeignKeyConstraint(["related_file_id"], ["files.id"]),
        sa.ForeignKeyConstraint(["related_job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_user_feedback_owner", "user_feedback", ["owner_user_id"])
    op.create_index("idx_user_feedback_status", "user_feedback", ["status"])
    op.create_index("idx_user_feedback_priority", "user_feedback", ["priority"])
    op.create_index("idx_user_feedback_created", "user_feedback", ["created_at"])
    op.create_index("idx_user_feedback_job", "user_feedback", ["related_job_id"])

    op.create_table(
        "feedback_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feedback_id", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('created','status_changed','priority_changed','assigned','commented','public_replied','closed','reopened')",
            name="ck_feedback_events_type",
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["feedback_id"], ["user_feedback.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_feedback_events_feedback", "feedback_events", ["feedback_id"])
    op.create_index("idx_feedback_events_actor", "feedback_events", ["actor_user_id"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_admin_audit_admin", "admin_audit_logs", ["admin_user_id"])
    op.create_index("idx_admin_audit_target", "admin_audit_logs", ["target_type", "target_id"])
    op.create_index("idx_admin_audit_created", "admin_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_admin_audit_created", table_name="admin_audit_logs")
    op.drop_index("idx_admin_audit_target", table_name="admin_audit_logs")
    op.drop_index("idx_admin_audit_admin", table_name="admin_audit_logs")
    op.drop_table("admin_audit_logs")

    op.drop_index("idx_feedback_events_actor", table_name="feedback_events")
    op.drop_index("idx_feedback_events_feedback", table_name="feedback_events")
    op.drop_table("feedback_events")

    op.drop_index("idx_user_feedback_job", table_name="user_feedback")
    op.drop_index("idx_user_feedback_created", table_name="user_feedback")
    op.drop_index("idx_user_feedback_priority", table_name="user_feedback")
    op.drop_index("idx_user_feedback_status", table_name="user_feedback")
    op.drop_index("idx_user_feedback_owner", table_name="user_feedback")
    op.drop_table("user_feedback")
