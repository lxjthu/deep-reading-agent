"""add bib entry language

Revision ID: 015_add_bib_entry_language
Revises: 014_add_translation_types
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_add_bib_entry_language"
down_revision: Union[str, None] = "014_add_translation_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bib_entries") as batch:
        batch.add_column(sa.Column("language", sa.String(), nullable=True))
        batch.create_check_constraint(
            "ck_bib_language",
            "language IS NULL OR language IN ('en','zh','other')",
        )


def downgrade() -> None:
    with op.batch_alter_table("bib_entries") as batch:
        batch.drop_constraint("ck_bib_language", type_="check")
        batch.drop_column("language")
