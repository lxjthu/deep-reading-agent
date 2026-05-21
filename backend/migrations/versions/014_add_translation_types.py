"""add translation job/artifact/prompt types

Revision ID: 014_add_translation_types
Revises: 013_expand_prompt_type_check
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "014_add_translation_types"
down_revision: Union[str, None] = "013_expand_prompt_type_check"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("jobs", recreate="always") as batch:
        batch.drop_constraint("ck_jobs_job_type", type_="check")
        batch.create_check_constraint(
            "ck_jobs_job_type",
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis','reference_trace','translation')",
        )

    with op.batch_alter_table("artifacts", recreate="always") as batch:
        batch.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch.create_check_constraint(
            "ck_artifacts_artifact_type",
            "artifact_type IN ('reading_step','reading_final','reading_extract',"
            "'filter_excel','compare_excel','compare_md','synthesis_md',"
            "'references_excel','references_with_citations_excel',"
            "'citation_trace_md','references_json','translation_md','translation_glossary')",
        )

    with op.batch_alter_table("prompt_templates") as batch:
        batch.drop_constraint("ck_prompt_templates_type", type_="check")
        batch.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter','compare','synthesis','ai_template','translation')",
        )


def downgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch:
        batch.drop_constraint("ck_prompt_templates_type", type_="check")
        batch.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter','compare','synthesis','ai_template')",
        )

    with op.batch_alter_table("artifacts", recreate="always") as batch:
        batch.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch.create_check_constraint(
            "ck_artifacts_artifact_type",
            "artifact_type IN ('reading_step','reading_final','reading_extract',"
            "'filter_excel','compare_excel','compare_md','synthesis_md',"
            "'references_excel','references_with_citations_excel',"
            "'citation_trace_md','references_json')",
        )

    with op.batch_alter_table("jobs", recreate="always") as batch:
        batch.drop_constraint("ck_jobs_job_type", type_="check")
        batch.create_check_constraint(
            "ck_jobs_job_type",
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis','reference_trace')",
        )
