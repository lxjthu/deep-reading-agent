"""add library chat prompt type

Revision ID: 016_add_library_chat_prompt_type
Revises: 015_add_bib_entry_language
Create Date: 2026-05-22
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "016_add_library_chat_prompt_type"
down_revision: Union[str, None] = "015_add_bib_entry_language"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch:
        batch.drop_constraint("ck_prompt_templates_type", type_="check")
        batch.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter','compare','synthesis',"
            "'ai_template','translation','library_chat')",
        )


def downgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch:
        batch.drop_constraint("ck_prompt_templates_type", type_="check")
        batch.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter','compare','synthesis',"
            "'ai_template','translation')",
        )
