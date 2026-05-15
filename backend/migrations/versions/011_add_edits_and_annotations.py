"""add reading_item_edits and annotations tables

Revision ID: 011_add_edits_and_annotations
Revises: 010_add_dim_set_is_shared
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011_add_edits_and_annotations"
down_revision: Union[str, None] = "010_add_dim_set_is_shared"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reading_item_edits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reading_item_id", sa.Integer(), sa.ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("edited_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("reading_item_id", "owner_user_id", name="uq_rie_item_owner"),
    )
    op.create_index("idx_rie_owner", "reading_item_edits", ["owner_user_id"])
    op.create_index("idx_rie_item", "reading_item_edits", ["reading_item_id"])

    op.create_table(
        "annotations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("bib_entry_id", sa.String(), nullable=True),
        sa.Column("selected_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("is_ai_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint(
            "source_type IN ('compare_card','ai_summary','library_note')",
            name="ck_annotations_source_type",
        ),
    )
    op.create_index("idx_annotations_owner", "annotations", ["owner_user_id"])
    op.create_index("idx_annotations_source", "annotations", ["source_type", "source_id"])
    op.create_index("idx_annotations_bib", "annotations", ["bib_entry_id"])
    op.create_index("idx_annotations_ai", "annotations", ["is_ai_generated"])

    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter','compare')",
        )


def downgrade() -> None:
    op.drop_table("annotations")
    op.drop_table("reading_item_edits")

    with op.batch_alter_table("prompt_templates") as batch_op:
        batch_op.drop_constraint("ck_prompt_templates_type", type_="check")
        batch_op.create_check_constraint(
            "ck_prompt_templates_type",
            "prompt_type IN ('quant','qual','long','filter')",
        )
