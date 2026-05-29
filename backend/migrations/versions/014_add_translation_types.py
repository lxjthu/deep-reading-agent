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


def _replace_check_constraint(table_name: str, name: str, sql: str, *, recreate_sqlite: bool = False) -> None:
    if recreate_sqlite and op.get_context().dialect.name == "sqlite":
        with op.batch_alter_table(table_name, recreate="always") as batch:
            batch.drop_constraint(name, type_="check")
            batch.create_check_constraint(name, sql)
        return

    op.drop_constraint(name, table_name, type_="check")
    op.create_check_constraint(name, table_name, sql)


def upgrade() -> None:
    _replace_check_constraint(
        "jobs",
        "ck_jobs_job_type",
        "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
        "'compare','synthesis','reference_trace','translation')",
        recreate_sqlite=True,
    )

    _replace_check_constraint(
        "artifacts",
        "ck_artifacts_artifact_type",
        "artifact_type IN ('reading_step','reading_final','reading_extract',"
        "'filter_excel','compare_excel','compare_md','synthesis_md',"
        "'references_excel','references_with_citations_excel',"
        "'citation_trace_md','references_json','translation_md','translation_glossary')",
        recreate_sqlite=True,
    )

    _replace_check_constraint(
        "prompt_templates",
        "ck_prompt_templates_type",
        "prompt_type IN ('quant','qual','long','filter','compare','synthesis','ai_template','translation')",
        recreate_sqlite=True,
    )


def downgrade() -> None:
    _replace_check_constraint(
        "prompt_templates",
        "ck_prompt_templates_type",
        "prompt_type IN ('quant','qual','long','filter','compare','synthesis','ai_template')",
        recreate_sqlite=True,
    )

    _replace_check_constraint(
        "artifacts",
        "ck_artifacts_artifact_type",
        "artifact_type IN ('reading_step','reading_final','reading_extract',"
        "'filter_excel','compare_excel','compare_md','synthesis_md',"
        "'references_excel','references_with_citations_excel',"
        "'citation_trace_md','references_json')",
        recreate_sqlite=True,
    )

    _replace_check_constraint(
        "jobs",
        "ck_jobs_job_type",
        "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
        "'compare','synthesis','reference_trace')",
        recreate_sqlite=True,
    )
