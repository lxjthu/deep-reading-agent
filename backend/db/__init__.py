"""Database package for the multi-user system.

Public interface:
    Base                 — SQLAlchemy declarative base
    engine               — async engine
    AsyncSessionLocal    — async session factory
    get_db               — FastAPI dependency yielding AsyncSession
    PROJECT_ROOT         — Path to repo root
    DB_PATH              — Path to sqlite file
    DATABASE_URL         — async sqlalchemy URL (aiosqlite)
    SYNC_DATABASE_URL    — sync sqlalchemy URL (used by Alembic)
"""
from .base import Base
from .session import (
    engine,
    AsyncSessionLocal,
    get_db,
    PROJECT_ROOT,
    DB_PATH,
    DB_DIR,
    DATABASE_URL,
    SYNC_DATABASE_URL,
)
from . import models  # noqa: F401  ensure all models are registered with Base.metadata

__all__ = [
    "Base",
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "PROJECT_ROOT",
    "DB_PATH",
    "DB_DIR",
    "DATABASE_URL",
    "SYNC_DATABASE_URL",
]
