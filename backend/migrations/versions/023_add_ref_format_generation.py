"""add reference format generation

Revision ID: 023_add_ref_format_generation
Revises: 022_add_library_chat_history
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_add_ref_format_generation"
down_revision: Union[str, None] = "022_add_library_chat_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JOB_TYPES = (
    "'filter','reading_long','reading_quant','reading_qual',"
    "'compare','synthesis','reference_trace','translation','translate_abstracts','library_chat','ref_format'"
)

OLD_JOB_TYPES = (
    "'filter','reading_long','reading_quant','reading_qual',"
    "'compare','synthesis','reference_trace','translation','translate_abstracts','library_chat'"
)

ARTIFACT_TYPES = (
    "'reading_step','reading_final','reading_extract',"
    "'filter_excel','compare_excel','compare_md','synthesis_md',"
    "'references_excel','references_with_citations_excel',"
    "'citation_trace_md','references_json','translation_md','translation_glossary',"
    "'library_chat_md','ref_format_md'"
)

OLD_ARTIFACT_TYPES = (
    "'reading_step','reading_final','reading_extract',"
    "'filter_excel','compare_excel','compare_md','synthesis_md',"
    "'references_excel','references_with_citations_excel',"
    "'citation_trace_md','references_json','translation_md','translation_glossary','library_chat_md'"
)

PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat','card_note','ref_format'"
)

OLD_PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat','card_note'"
)


def upgrade() -> None:
    op.create_table(
        "ref_format_presets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("format_rules", sa.Text(), nullable=False),
        sa.Column("detected_format_name", sa.String(), nullable=True),
        sa.Column("entry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("owner_user_id", "name", name="uq_rfp_owner_name"),
    )
    op.create_index("idx_rfp_owner", "ref_format_presets", ["owner_user_id"])

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

    op.drop_index("idx_rfp_owner", table_name="ref_format_presets")
    op.drop_table("ref_format_presets")
