"""add library_chat job_type and artifact_type

Revision ID: 022_add_library_chat_history
Revises: 021_add_feedback_admin_tables
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "022_add_library_chat_history"
down_revision: Union[str, None] = "021_add_feedback_admin_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_TYPES = (
    "'filter','reading_long','reading_quant','reading_qual',"
    "'compare','synthesis','reference_trace','translation','translate_abstracts','library_chat'"
)

OLD_JOB_TYPES = (
    "'filter','reading_long','reading_quant','reading_qual',"
    "'compare','synthesis','reference_trace','translation','translate_abstracts'"
)

ARTIFACT_TYPES = (
    "'reading_step','reading_final','reading_extract',"
    "'filter_excel','compare_excel','compare_md','synthesis_md',"
    "'references_excel','references_with_citations_excel',"
    "'citation_trace_md','references_json','translation_md','translation_glossary','library_chat_md'"
)

OLD_ARTIFACT_TYPES = (
    "'reading_step','reading_final','reading_extract',"
    "'filter_excel','compare_excel','compare_md','synthesis_md',"
    "'references_excel','references_with_citations_excel',"
    "'citation_trace_md','references_json','translation_md','translation_glossary'"
)

JBE_ROLES = "'target','compare_member','synthesis_member','reference_source','library_chat_member'"
OLD_JBE_ROLES = "'target','compare_member','synthesis_member','reference_source'"


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("ck_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_jobs_job_type", f"job_type IN ({JOB_TYPES})")

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch_op.create_check_constraint("ck_artifacts_artifact_type", f"artifact_type IN ({ARTIFACT_TYPES})")

    with op.batch_alter_table("job_bib_entries") as batch_op:
        batch_op.drop_constraint("ck_jbe_role", type_="check")
        batch_op.create_check_constraint("ck_jbe_role", f"role IN ({JBE_ROLES})")


def downgrade() -> None:
    with op.batch_alter_table("job_bib_entries") as batch_op:
        batch_op.drop_constraint("ck_jbe_role", type_="check")
        batch_op.create_check_constraint("ck_jbe_role", f"role IN ({OLD_JBE_ROLES})")

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch_op.create_check_constraint("ck_artifacts_artifact_type", f"artifact_type IN ({OLD_ARTIFACT_TYPES})")

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("ck_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_jobs_job_type", f"job_type IN ({OLD_JOB_TYPES})")
