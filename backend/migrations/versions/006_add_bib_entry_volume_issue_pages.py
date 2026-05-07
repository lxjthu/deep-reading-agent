"""add volume issue pages to bib_entries

Revision ID: 006_add_bib_entry_volume_issue_pages
Revises: 005_add_reference_trace_tables
Create Date: 2026-05-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "006_add_bib_entry_volume_issue_pages"
down_revision: Union[str, None] = "005_add_reference_trace_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bib_entries") as batch_op:
        batch_op.add_column(sa.Column("volume", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("issue", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("pages", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bib_entries") as batch_op:
        batch_op.drop_column("pages")
        batch_op.drop_column("issue")
        batch_op.drop_column("volume")
