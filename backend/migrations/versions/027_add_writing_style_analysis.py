"""add writing style analysis types

Revision ID: 027_add_writing_style_analysis
Revises: 026_add_reading_source_evidence
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "027_add_writing_style_analysis"
down_revision: Union[str, None] = "026_add_reading_source_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_TYPES = (
    "'filter','reading_long','reading_quant','reading_qual',"
    "'compare','synthesis','reference_trace','translation','translate_abstracts','library_chat','ref_format','writing_style'"
)
OLD_JOB_TYPES = (
    "'filter','reading_long','reading_quant','reading_qual',"
    "'compare','synthesis','reference_trace','translation','translate_abstracts','library_chat','ref_format'"
)
ARTIFACT_TYPES = (
    "'reading_step','reading_final','reading_extract',"
    "'filter_excel','compare_excel','compare_md','synthesis_md',"
    "'references_excel','references_with_citations_excel',"
    "'citation_trace_md','references_json','translation_md','translation_glossary',"
    "'library_chat_md','ref_format_md','writing_style_md'"
)
OLD_ARTIFACT_TYPES = (
    "'reading_step','reading_final','reading_extract',"
    "'filter_excel','compare_excel','compare_md','synthesis_md',"
    "'references_excel','references_with_citations_excel',"
    "'citation_trace_md','references_json','translation_md','translation_glossary',"
    "'library_chat_md','ref_format_md'"
)
PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat','journal_kb','card_note','ref_format','writing_style'"
)
OLD_PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat','journal_kb','card_note','ref_format'"
)


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("ck_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_jobs_job_type", f"job_type IN ({JOB_TYPES})")

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch_op.create_check_constraint("ck_artifacts_artifact_type", f"artifact_type IN ({ARTIFACT_TYPES})")

    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint("ck_prompt_templates_type", f"prompt_type IN ({PROMPT_TYPES})")


def downgrade() -> None:
    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint("ck_prompt_templates_type", f"prompt_type IN ({OLD_PROMPT_TYPES})")

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch_op.create_check_constraint("ck_artifacts_artifact_type", f"artifact_type IN ({OLD_ARTIFACT_TYPES})")

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("ck_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_jobs_job_type", f"job_type IN ({OLD_JOB_TYPES})")
