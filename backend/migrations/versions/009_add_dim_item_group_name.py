"""add group_name to dimension_items

Revision ID: 009_add_dim_item_group_name
Revises: 008_add_dimension_templates
Create Date: 2026-05-10
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009_add_dim_item_group_name"
down_revision: Union[str, None] = "008_add_dimension_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dimension_items",
        sa.Column("group_name", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dimension_items", "group_name")
