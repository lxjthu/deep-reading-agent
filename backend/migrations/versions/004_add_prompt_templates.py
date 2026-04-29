"""add prompt_templates for prompt center

Revision ID: 004_add_prompt_templates
Revises: 003_add_reading_items
Create Date: 2026-04-29
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "004_add_prompt_templates"
down_revision: Union[str, None] = "003_add_reading_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("prompt_type", sa.String(), nullable=False),
        sa.Column("prompt_key", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
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
        sa.CheckConstraint("scope IN ('system','user')", name="ck_prompt_templates_scope"),
        sa.CheckConstraint(
            "prompt_type IN ('quant','qual','long','filter')",
            name="ck_prompt_templates_type",
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "prompt_type",
            "prompt_key",
            name="uq_prompt_templates_owner_type_key",
        ),
    )
    op.create_index("idx_prompt_templates_scope", "prompt_templates", ["scope"])
    op.create_index("idx_prompt_templates_owner", "prompt_templates", ["owner_user_id"])
    op.create_index(
        "idx_prompt_templates_type_key",
        "prompt_templates",
        ["prompt_type", "prompt_key"],
    )


def downgrade() -> None:
    op.drop_index("idx_prompt_templates_type_key", table_name="prompt_templates")
    op.drop_index("idx_prompt_templates_owner", table_name="prompt_templates")
    op.drop_index("idx_prompt_templates_scope", table_name="prompt_templates")
    op.drop_table("prompt_templates")
