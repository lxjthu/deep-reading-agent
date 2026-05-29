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


def _rebuild_table_sqlite(table: str, new_ddl: str) -> None:
    ctx = op.get_context()
    if ctx.dialect.name != "sqlite":
        return
    bind = op.get_bind()
    tmp = f"_tmp_{table}"
    bind.exec_driver_sql(f"ALTER TABLE {table} RENAME TO {tmp}")
    bind.exec_driver_sql(new_ddl)
    cols = bind.exec_driver_sql(f"PRAGMA table_info({tmp})").fetchall()
    col_names = ", ".join(c[1] for c in cols)
    bind.exec_driver_sql(f"INSERT INTO {table} ({col_names}) SELECT {col_names} FROM {tmp}")
    bind.exec_driver_sql(f"DROP TABLE {tmp}")


JBE_TABLE_DDL = (
    'CREATE TABLE job_bib_entries ('
    'id INTEGER NOT NULL, job_id VARCHAR NOT NULL, bib_entry_id VARCHAR NOT NULL, '
    'role VARCHAR NOT NULL, sort_order INTEGER DEFAULT 0 NOT NULL, '
    'PRIMARY KEY (id), '
    'CONSTRAINT uq_jbe_unique UNIQUE (job_id, bib_entry_id, role), '
    f'CONSTRAINT ck_jbe_role CHECK (role IN ({JBE_ROLES})), '
    'FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, '
    'FOREIGN KEY(bib_entry_id) REFERENCES bib_entries (id) ON DELETE CASCADE)'
)

OLD_JBE_TABLE_DDL = (
    'CREATE TABLE job_bib_entries ('
    'id INTEGER NOT NULL, job_id VARCHAR NOT NULL, bib_entry_id VARCHAR NOT NULL, '
    'role VARCHAR NOT NULL, sort_order INTEGER DEFAULT 0 NOT NULL, '
    'PRIMARY KEY (id), '
    'CONSTRAINT uq_jbe_unique UNIQUE (job_id, bib_entry_id, role), '
    f'CONSTRAINT ck_jbe_role CHECK (role IN ({OLD_JBE_ROLES})), '
    'FOREIGN KEY(job_id) REFERENCES jobs (id) ON DELETE CASCADE, '
    'FOREIGN KEY(bib_entry_id) REFERENCES bib_entries (id) ON DELETE CASCADE)'
)


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("ck_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_jobs_job_type", f"job_type IN ({JOB_TYPES})")

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch_op.create_check_constraint("ck_artifacts_artifact_type", f"artifact_type IN ({ARTIFACT_TYPES})")

    _rebuild_table_sqlite("job_bib_entries", JBE_TABLE_DDL)

    ctx = op.get_context()
    if ctx.dialect.name != "sqlite":
        with op.batch_alter_table("job_bib_entries") as batch_op:
            batch_op.drop_constraint("ck_jbe_role", type_="check")
            batch_op.create_check_constraint("ck_jbe_role", f"role IN ({JBE_ROLES})")


def downgrade() -> None:
    _rebuild_table_sqlite("job_bib_entries", OLD_JBE_TABLE_DDL)

    ctx = op.get_context()
    if ctx.dialect.name != "sqlite":
        with op.batch_alter_table("job_bib_entries") as batch_op:
            batch_op.drop_constraint("ck_jbe_role", type_="check")
            batch_op.create_check_constraint("ck_jbe_role", f"role IN ({OLD_JBE_ROLES})")

    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.drop_constraint("ck_artifacts_artifact_type", type_="check")
        batch_op.create_check_constraint("ck_artifacts_artifact_type", f"artifact_type IN ({OLD_ARTIFACT_TYPES})")

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("ck_jobs_job_type", type_="check")
        batch_op.create_check_constraint("ck_jobs_job_type", f"job_type IN ({OLD_JOB_TYPES})")
