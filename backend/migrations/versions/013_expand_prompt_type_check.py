"""expand prompt_type check constraint for synthesis and ai_template

Revision ID: 013_expand_prompt_type_check
Revises: 012_add_dimension_set_reading_availability
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "013_expand_prompt_type_check"
down_revision: Union[str, None] = "012_add_dimension_set_reading_availability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch:
        batch.drop_constraint("ck_prompt_templates_type", type_="check")
        batch.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter','compare','synthesis','ai_template')",
        )


def downgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch:
        batch.drop_constraint("ck_prompt_templates_type", type_="check")
        batch.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter','compare')",
        )
