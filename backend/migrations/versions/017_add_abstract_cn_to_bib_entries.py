"""add abstract_cn to bib_entries

Revision ID: 017_add_abstract_cn
Revises: 016_add_library_chat_prompt_type
Create Date: 2026-05-22 18:35:28.217236
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '017_add_abstract_cn'
down_revision: Union[str, None] = '016_add_library_chat_prompt_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bib_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('abstract_cn', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bib_entries', schema=None) as batch_op:
        batch_op.drop_column('abstract_cn')
