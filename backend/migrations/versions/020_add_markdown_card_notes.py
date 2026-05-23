"""add markdown card notes

Revision ID: 020_add_markdown_card_notes
Revises: 019_add_agent_sessions
Create Date: 2026-05-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_add_markdown_card_notes"
down_revision: Union[str, None] = "019_add_agent_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat','card_note'"
)

OLD_PROMPT_TYPES = (
    "'quant','qual','long','filter','compare','synthesis','ai_template',"
    "'translation','library_chat'"
)


def upgrade() -> None:
    with op.batch_alter_table("bib_entries") as batch_op:
        batch_op.add_column(sa.Column("markdown_source_file_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_bib_entries_markdown_source_file_id_files",
            "files",
            ["markdown_source_file_id"],
            ["id"],
        )
    op.create_index("idx_bib_markdown_source", "bib_entries", ["markdown_source_file_id"])

    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint(
            "ck_prompt_templates_type",
            f"prompt_type IN ({PROMPT_TYPES})",
        )

    op.create_table(
        "card_notes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("source_bib_entry_id", sa.String(), nullable=False),
        sa.Column("source_version", sa.String(), nullable=False),
        sa.Column("source_markdown_file_id", sa.String(), nullable=True),
        sa.Column("source_translation_artifact_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column("context_before", sa.Text(), nullable=True),
        sa.Column("context_after", sa.Text(), nullable=True),
        sa.Column("user_prompt", sa.Text(), nullable=True),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("source_version IN ('original','translated')", name="ck_card_notes_source_version"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_bib_entry_id"], ["bib_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_markdown_file_id"], ["files.id"]),
        sa.ForeignKeyConstraint(["source_translation_artifact_id"], ["artifacts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_card_notes_owner", "card_notes", ["owner_user_id"])
    op.create_index("idx_card_notes_bib", "card_notes", ["source_bib_entry_id"])
    op.create_index("idx_card_notes_created", "card_notes", ["created_at"])
    op.create_index("idx_card_notes_expires", "card_notes", ["expires_at"])
    op.create_index("idx_card_notes_translation", "card_notes", ["source_translation_artifact_id"])


def downgrade() -> None:
    op.drop_index("idx_card_notes_translation", table_name="card_notes")
    op.drop_index("idx_card_notes_expires", table_name="card_notes")
    op.drop_index("idx_card_notes_created", table_name="card_notes")
    op.drop_index("idx_card_notes_bib", table_name="card_notes")
    op.drop_index("idx_card_notes_owner", table_name="card_notes")
    op.drop_table("card_notes")

    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint(
            "ck_prompt_templates_type",
            f"prompt_type IN ({OLD_PROMPT_TYPES})",
        )

    op.drop_index("idx_bib_markdown_source", table_name="bib_entries")
    with op.batch_alter_table("bib_entries") as batch_op:
        batch_op.drop_constraint("fk_bib_entries_markdown_source_file_id_files", type_="foreignkey")
        batch_op.drop_column("markdown_source_file_id")
