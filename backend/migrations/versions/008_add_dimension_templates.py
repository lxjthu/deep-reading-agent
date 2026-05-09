"""add dimension_templates and template_items

Revision ID: 008_add_dimension_templates
Revises: 007_add_dimension_tables
Create Date: 2026-05-09
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "008_add_dimension_templates"
down_revision: Union[str, None] = "007_add_dimension_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dimension_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("dim_count", sa.Integer(), nullable=False),
        sa.Column("preview_json", sa.Text(), nullable=True),
        sa.Column("group_config", sa.Text(), nullable=True),
        sa.Column("is_featured", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dim_templates_category", "dimension_templates", ["category"])
    op.create_index("idx_dim_templates_featured", "dimension_templates", ["is_featured"])

    op.create_table(
        "template_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("dim_key", sa.String(), nullable=False),
        sa.Column("dim_name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("default_question", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("group_name", sa.String(), nullable=True),
        sa.Column("is_builtin", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["template_id"], ["dimension_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "dim_key", name="uq_template_items_key"),
    )
    op.create_index("idx_template_items_template", "template_items", ["template_id"])


def downgrade() -> None:
    op.drop_index("idx_template_items_template", table_name="template_items")
    op.drop_table("template_items")
    op.drop_index("idx_dim_templates_featured", table_name="dimension_templates")
    op.drop_index("idx_dim_templates_category", table_name="dimension_templates")
    op.drop_table("dimension_templates")
