"""add bib_attachments table + expand card_notes.source_version

Revision ID: 025_add_bib_attachments
Revises: 024_add_journal_kb_prompt_type
Create Date: 2026-06-01
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "025_add_bib_attachments"
down_revision: Union[str, None] = "024_add_journal_kb_prompt_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bib_attachments",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("bib_entry_id", sa.String, sa.ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", sa.String, sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("owner_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("bib_entry_id", "file_id", name="uq_bib_att_entry_file"),
    )
    op.create_index("idx_bib_att_entry", "bib_attachments", ["bib_entry_id"])
    op.create_index("idx_bib_att_owner", "bib_attachments", ["owner_user_id"])
    op.create_index("idx_bib_att_expires", "bib_attachments", ["expires_at"])

    with op.batch_alter_table("card_notes") as batch_op:
        batch_op.drop_constraint("ck_card_notes_source_version", type_="check")
        batch_op.create_check_constraint(
            "ck_card_notes_source_version",
            "source_version IN ('original','translated','attachment')",
        )


def downgrade() -> None:
    op.drop_table("bib_attachments")

    with op.batch_alter_table("card_notes") as batch_op:
        batch_op.drop_constraint("ck_card_notes_source_version", type_="check")
        batch_op.create_check_constraint(
            "ck_card_notes_source_version",
            "source_version IN ('original','translated')",
        )
