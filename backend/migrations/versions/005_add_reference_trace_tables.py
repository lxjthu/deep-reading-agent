"""add reference trace tables

Revision ID: 005_add_reference_trace_tables
Revises: 004_add_prompt_templates
Create Date: 2026-04-30
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "005_add_reference_trace_tables"
down_revision: Union[str, None] = "004_add_prompt_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _replace_check_constraint(table_name: str, old_sql: str, new_sql: str) -> None:
    with op.batch_alter_table(table_name, recreate="always") as batch_op:
        batch_op.drop_constraint(old_sql, type_="check")
        batch_op.create_check_constraint(old_sql, new_sql)


def upgrade() -> None:
    op.create_table(
        "bib_references",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "source_bib_entry_id",
            sa.String(),
            sa.ForeignKey("bib_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("reference_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("authors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("journal", sa.Text(), nullable=True),
        sa.Column("volume", sa.String(), nullable=True),
        sa.Column("issue", sa.String(), nullable=True),
        sa.Column("pages", sa.String(), nullable=True),
        sa.Column("doi", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("dedup_key", sa.String(), nullable=True),
        sa.Column("matched_bib_entry_id", sa.String(), sa.ForeignKey("bib_entries.id"), nullable=True),
        sa.Column("match_method", sa.String(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("idx_bib_refs_owner", "bib_references", ["owner_user_id"])
    op.create_index("idx_bib_refs_source_bib", "bib_references", ["source_bib_entry_id"])
    op.create_index("idx_bib_refs_source_job", "bib_references", ["source_job_id"])
    op.create_index("idx_bib_refs_matched_bib", "bib_references", ["matched_bib_entry_id"])
    op.create_index("idx_bib_refs_doi", "bib_references", ["doi"])
    op.create_index("idx_bib_refs_dedup", "bib_references", ["dedup_key"])

    op.create_table(
        "bib_reference_citations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "source_bib_entry_id",
            sa.String(),
            sa.ForeignKey("bib_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bib_reference_id",
            sa.String(),
            sa.ForeignKey("bib_references.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_job_id",
            sa.String(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("citation_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_label", sa.String(), nullable=True),
        sa.Column("section_label", sa.String(), nullable=True),
        sa.Column("paragraph_label", sa.String(), nullable=True),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("quote_text_zh", sa.Text(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("match_method", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("idx_brc_owner", "bib_reference_citations", ["owner_user_id"])
    op.create_index("idx_brc_source_bib", "bib_reference_citations", ["source_bib_entry_id"])
    op.create_index("idx_brc_reference", "bib_reference_citations", ["bib_reference_id"])
    op.create_index("idx_brc_source_job", "bib_reference_citations", ["source_job_id"])

    _replace_check_constraint(
        "jobs",
        "ck_jobs_job_type",
        "job_type IN ('filter','reading_long','reading_quant','reading_qual','compare','synthesis','reference_trace')",
    )
    _replace_check_constraint(
        "job_bib_entries",
        "ck_jbe_role",
        "role IN ('target','compare_member','synthesis_member','reference_source')",
    )
    _replace_check_constraint(
        "artifacts",
        "ck_artifacts_artifact_type",
        "artifact_type IN ('reading_step','reading_final','reading_extract','filter_excel','compare_excel','compare_md','synthesis_md','references_excel','references_with_citations_excel','citation_trace_md','references_json')",
    )


def downgrade() -> None:
    _replace_check_constraint(
        "artifacts",
        "ck_artifacts_artifact_type",
        "artifact_type IN ('reading_step','reading_final','reading_extract','filter_excel','compare_excel','compare_md','synthesis_md')",
    )
    _replace_check_constraint(
        "job_bib_entries",
        "ck_jbe_role",
        "role IN ('target','compare_member','synthesis_member')",
    )
    _replace_check_constraint(
        "jobs",
        "ck_jobs_job_type",
        "job_type IN ('filter','reading_long','reading_quant','reading_qual','compare','synthesis')",
    )

    op.drop_index("idx_brc_source_job", table_name="bib_reference_citations")
    op.drop_index("idx_brc_reference", table_name="bib_reference_citations")
    op.drop_index("idx_brc_source_bib", table_name="bib_reference_citations")
    op.drop_index("idx_brc_owner", table_name="bib_reference_citations")
    op.drop_table("bib_reference_citations")

    op.drop_index("idx_bib_refs_dedup", table_name="bib_references")
    op.drop_index("idx_bib_refs_doi", table_name="bib_references")
    op.drop_index("idx_bib_refs_matched_bib", table_name="bib_references")
    op.drop_index("idx_bib_refs_source_job", table_name="bib_references")
    op.drop_index("idx_bib_refs_source_bib", table_name="bib_references")
    op.drop_index("idx_bib_refs_owner", table_name="bib_references")
    op.drop_table("bib_references")
