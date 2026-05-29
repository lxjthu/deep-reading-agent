"""add journal_kb prompt type

Revision ID: 024_add_journal_kb_prompt_type
Revises: 023_add_ref_format_generation
Create Date: 2026-05-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "024_add_journal_kb_prompt_type"
down_revision: Union[str, None] = "023_add_ref_format_generation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat','journal_kb','card_note','ref_format'"
)

OLD_PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat','card_note','ref_format'"
)


def upgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint("ck_prompt_templates_type", f"prompt_type IN ({PROMPT_TYPES})")


def downgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint("ck_prompt_templates_type", f"prompt_type IN ({OLD_PROMPT_TYPES})")
