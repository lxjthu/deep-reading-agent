"""add library_chat job_type and artifact_type

Revision ID: 022_add_library_chat_history
Revises: 021_add_feedback_admin_tables
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_add_library_chat_history"
down_revision: Union[str, None] = "021_add_feedback_admin_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_table(
        "jobs",
        sa.CheckConstraint(
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis','reference_trace','translation','translate_abstracts','library_chat')",
            name="ck_jobs_job_type",
        ),
    )
    op.alter_table(
        "artifacts",
        sa.CheckConstraint(
            "artifact_type IN ('reading_step','reading_final','reading_extract',"
            "'filter_excel','compare_excel','compare_md','synthesis_md',"
            "'references_excel','references_with_citations_excel',"
            "'citation_trace_md','references_json','translation_md','translation_glossary','library_chat_md')",
            name="ck_artifacts_artifact_type",
        ),
    )


def downgrade() -> None:
    op.alter_table(
        "artifacts",
        sa.CheckConstraint(
            "artifact_type IN ('reading_step','reading_final','reading_extract',"
            "'filter_excel','compare_excel','compare_md','synthesis_md',"
            "'references_excel','references_with_citations_excel',"
            "'citation_trace_md','references_json','translation_md','translation_glossary')",
            name="ck_artifacts_artifact_type",
        ),
    )
    op.alter_table(
        "jobs",
        sa.CheckConstraint(
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis','reference_trace','translation','translate_abstracts')",
            name="ck_jobs_job_type",
        ),
    )
