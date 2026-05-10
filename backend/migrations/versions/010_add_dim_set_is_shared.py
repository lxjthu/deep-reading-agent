"""add is_shared to dimension_sets

Revision ID: 010_add_dim_set_is_shared
Revises: 009_add_dim_item_group_name
Create Date: 2026-05-10
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010_add_dim_set_is_shared"
down_revision: Union[str, None] = "009_add_dim_item_group_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dimension_sets",
        sa.Column("is_shared", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("dimension_sets", "is_shared")
