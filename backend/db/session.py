"""Database engine and session management."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_DIR = PROJECT_ROOT / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "app.sqlite"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{DB_PATH.as_posix()}",
)

if DATABASE_URL.startswith("postgresql+asyncpg"):
    SYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)
elif DATABASE_URL.startswith("sqlite+aiosqlite"):
    SYNC_DATABASE_URL = DATABASE_URL.replace("sqlite+aiosqlite", "sqlite", 1)
elif DATABASE_URL.startswith("sqlite"):
    SYNC_DATABASE_URL = DATABASE_URL
else:
    SYNC_DATABASE_URL = DATABASE_URL

engine_kwargs = {"echo": False, "future": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update(
        poolclass=NullPool,
        pool_pre_ping=True,
    )

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an AsyncSession and ensures it is closed."""
    async with AsyncSessionLocal() as session:
        yield session
