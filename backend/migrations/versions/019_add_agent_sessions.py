"""add agent sessions

Revision ID: 019_add_agent_sessions
Revises: 018_translate_abstracts
Create Date: 2026-05-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_add_agent_sessions"
down_revision: Union[str, None] = "018_translate_abstracts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="active", nullable=False),
        sa.Column("last_summary", sa.Text(), nullable=True),
        sa.Column("last_state_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('active','archived')", name="ck_agent_sessions_status"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_sessions_owner", "agent_sessions", ["owner_user_id"])
    op.create_index("idx_agent_sessions_updated", "agent_sessions", ["updated_at"])
    op.create_index("idx_agent_sessions_expires", "agent_sessions", ["expires_at"])

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('user','assistant','tool','system')", name="ck_agent_messages_role"),
        sa.CheckConstraint(
            "event_type IN ('message','tool_call','tool_result','proposal','confirmation','error')",
            name="ck_agent_messages_event_type",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_messages_session", "agent_messages", ["session_id"])
    op.create_index("idx_agent_messages_owner", "agent_messages", ["owner_user_id"])
    op.create_index("idx_agent_messages_expires", "agent_messages", ["expires_at"])

    op.create_table(
        "agent_action_proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("arguments_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("preview_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','rejected','expired','executed','failed')",
            name="ck_agent_proposals_status",
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_agent_proposals_session", "agent_action_proposals", ["session_id"])
    op.create_index("idx_agent_proposals_status", "agent_action_proposals", ["status"])
    op.create_index("idx_agent_proposals_owner", "agent_action_proposals", ["owner_user_id"])
    op.create_index("idx_agent_proposals_expires", "agent_action_proposals", ["expires_at"])


def downgrade() -> None:
    op.drop_index("idx_agent_proposals_expires", table_name="agent_action_proposals")
    op.drop_index("idx_agent_proposals_owner", table_name="agent_action_proposals")
    op.drop_index("idx_agent_proposals_status", table_name="agent_action_proposals")
    op.drop_index("idx_agent_proposals_session", table_name="agent_action_proposals")
    op.drop_table("agent_action_proposals")

    op.drop_index("idx_agent_messages_expires", table_name="agent_messages")
    op.drop_index("idx_agent_messages_owner", table_name="agent_messages")
    op.drop_index("idx_agent_messages_session", table_name="agent_messages")
    op.drop_table("agent_messages")

    op.drop_index("idx_agent_sessions_expires", table_name="agent_sessions")
    op.drop_index("idx_agent_sessions_updated", table_name="agent_sessions")
    op.drop_index("idx_agent_sessions_owner", table_name="agent_sessions")
    op.drop_table("agent_sessions")
