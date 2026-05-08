"""add dimension_sets and dimension_items tables

Revision ID: 007_add_dimension_tables
Revises: 006_add_bib_entry_volume_issue_pages
Create Date: 2026-05-08
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "007_add_dimension_tables"
down_revision: Union[str, None] = "006_add_bib_entry_volume_issue_pages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dimension_sets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_system", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_dim_sets_owner_name"),
    )
    op.create_index("idx_dim_sets_owner", "dimension_sets", ["owner_user_id"])
    op.create_index("idx_dim_sets_default", "dimension_sets", ["owner_user_id", "is_default"])

    op.create_table(
        "dimension_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("set_id", sa.Integer(), nullable=False),
        sa.Column("dim_key", sa.String(), nullable=False),
        sa.Column("dim_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("default_question", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_builtin", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["set_id"], ["dimension_sets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("set_id", "dim_key", name="uq_dim_items_set_key"),
    )
    op.create_index("idx_dim_items_set", "dimension_items", ["set_id"])
    op.create_index("idx_dim_items_builtin", "dimension_items", ["set_id", "is_builtin"])


def downgrade() -> None:
    op.drop_index("idx_dim_items_builtin", table_name="dimension_items")
    op.drop_index("idx_dim_items_set", table_name="dimension_items")
    op.drop_table("dimension_items")
    op.drop_index("idx_dim_sets_default", table_name="dimension_sets")
    op.drop_index("idx_dim_sets_owner", table_name="dimension_sets")
    op.drop_table("dimension_sets")
