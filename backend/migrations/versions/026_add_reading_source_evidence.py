"""add reading source evidence table

Revision ID: 026_add_reading_source_evidence
Revises: 025_add_bib_attachments
Create Date: 2026-06-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "026_add_reading_source_evidence"
down_revision: Union[str, None] = "025_add_bib_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reading_source_evidence",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bib_entry_id", sa.String, sa.ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reading_item_id", sa.Integer, sa.ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file_id", sa.String, sa.ForeignKey("files.id"), nullable=True),
        sa.Column("source_version", sa.String, nullable=False, server_default="original"),
        sa.Column("source_tier", sa.String, nullable=False, server_default="P0"),
        sa.Column("validation_status", sa.String, nullable=False),
        sa.Column("mode", sa.String, nullable=False),
        sa.Column("item_key", sa.String, nullable=False),
        sa.Column("item_label", sa.String, nullable=False),
        sa.Column("evidence_role", sa.String, nullable=False, server_default="support"),
        sa.Column("claim_text", sa.Text, nullable=True),
        sa.Column("quote_text", sa.Text, nullable=False),
        sa.Column("quote_hash", sa.String, nullable=False),
        sa.Column("page_label", sa.String, nullable=True),
        sa.Column("section_hint", sa.Text, nullable=True),
        sa.Column("heading_path", sa.Text, nullable=True),
        sa.Column("char_start", sa.Integer, nullable=True),
        sa.Column("char_end", sa.Integer, nullable=True),
        sa.Column("match_score", sa.Float, nullable=True),
        sa.Column("metadata_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(
            "source_version IN ('original','translated')",
            name="ck_rse_source_version",
        ),
        sa.CheckConstraint(
            "source_tier IN ('P0','P1','P2','P3')",
            name="ck_rse_source_tier",
        ),
        sa.CheckConstraint(
            "validation_status IN ('exact','fuzzy','unmatched')",
            name="ck_rse_validation_status",
        ),
        sa.UniqueConstraint("reading_item_id", "quote_hash", name="uq_rse_item_quote"),
    )
    op.create_index("idx_rse_owner", "reading_source_evidence", ["owner_user_id"])
    op.create_index("idx_rse_bib", "reading_source_evidence", ["bib_entry_id"])
    op.create_index("idx_rse_job", "reading_source_evidence", ["job_id"])
    op.create_index("idx_rse_item", "reading_source_evidence", ["reading_item_id"])
    op.create_index(
        "idx_rse_tier_status",
        "reading_source_evidence",
        ["source_tier", "validation_status"],
    )
    op.create_index("idx_rse_expires", "reading_source_evidence", ["expires_at"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX idx_rse_quote_trgm "
            "ON reading_source_evidence USING gin (quote_text gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX idx_rse_claim_trgm "
            "ON reading_source_evidence USING gin (claim_text gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX idx_rse_fts_simple ON reading_source_evidence USING gin "
            "(to_tsvector('simple', "
            "coalesce(quote_text, '') || ' ' || "
            "coalesce(claim_text, '') || ' ' || "
            "coalesce(section_hint, '')))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_rse_fts_simple")
        op.execute("DROP INDEX IF EXISTS idx_rse_claim_trgm")
        op.execute("DROP INDEX IF EXISTS idx_rse_quote_trgm")
    op.drop_table("reading_source_evidence")
