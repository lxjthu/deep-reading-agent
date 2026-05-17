"""add reading availability flag to dimension_sets

Revision ID: 012_add_dimension_set_reading_availability
Revises: 011_add_edits_and_annotations
Create Date: 2026-05-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012_add_dimension_set_reading_availability"
down_revision: Union[str, None] = "011_add_edits_and_annotations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info({table_name})")).fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    if not _column_exists("dimension_sets", "is_available_for_reading"):
        op.add_column(
            "dimension_sets",
            sa.Column(
                "is_available_for_reading",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )


def downgrade() -> None:
    if _column_exists("dimension_sets", "is_available_for_reading"):
        op.drop_column("dimension_sets", "is_available_for_reading")
