"""add reading_items for structured reading outputs

Revision ID: 003_add_reading_items
Revises: 002_add_users_token_version
Create Date: 2026-04-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "003_add_reading_items"
down_revision: Union[str, None] = "002_add_users_token_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reading_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "bib_entry_id",
            sa.String(),
            sa.ForeignKey("bib_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("section_type", sa.String(), nullable=False),
        sa.Column("parent_key", sa.String(), nullable=True),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("item_label", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.CheckConstraint(
            "mode IN ('long','quant','qual')",
            name="ck_reading_items_mode",
        ),
        sa.CheckConstraint(
            "section_type IN ('dimension','step','subquestion','custom')",
            name="ck_reading_items_section_type",
        ),
        sa.UniqueConstraint("job_id", "item_key", name="uq_reading_items_job_key"),
    )
    op.create_index("idx_reading_items_owner", "reading_items", ["owner_user_id"])
    op.create_index("idx_reading_items_bib", "reading_items", ["bib_entry_id"])
    op.create_index("idx_reading_items_job", "reading_items", ["job_id"])
    op.create_index("idx_reading_items_mode", "reading_items", ["mode"])
    op.create_index("idx_reading_items_parent", "reading_items", ["parent_key"])


def downgrade() -> None:
    op.drop_index("idx_reading_items_parent", table_name="reading_items")
    op.drop_index("idx_reading_items_mode", table_name="reading_items")
    op.drop_index("idx_reading_items_job", table_name="reading_items")
    op.drop_index("idx_reading_items_bib", table_name="reading_items")
    op.drop_index("idx_reading_items_owner", table_name="reading_items")
    op.drop_table("reading_items")
