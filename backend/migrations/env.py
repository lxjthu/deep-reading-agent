"""Alembic environment configuration.

Uses the synchronous SQLAlchemy URL exposed by backend.db.session for
migration execution; the application itself runs against the async URL.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `backend` package importable when alembic is invoked from backend/
HERE = Path(__file__).resolve().parent              # backend/migrations
BACKEND_DIR = HERE.parent                           # backend
PROJECT_ROOT = BACKEND_DIR.parent                   # repo root
for path in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from db import Base, SYNC_DATABASE_URL  # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=SYNC_DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(255) NOT NULL PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "ALTER TABLE alembic_version "
                "ALTER COLUMN version_num TYPE VARCHAR(255)"
            )
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
