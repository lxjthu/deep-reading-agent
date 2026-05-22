"""add translate_abstracts to job_type check

Revision ID: 018_translate_abstracts
Revises: 017_add_abstract_cn
Create Date: 2026-05-22
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '018_translate_abstracts'
down_revision: Union[str, None] = '017_add_abstract_cn'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_jobs_job_type', type_='check')
        batch_op.create_check_constraint(
            'ck_jobs_job_type',
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis','reference_trace','translation','translate_abstracts')",
        )


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_jobs_job_type', type_='check')
        batch_op.create_check_constraint(
            'ck_jobs_job_type',
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis','reference_trace','translation')",
        )
