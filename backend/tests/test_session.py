from __future__ import annotations

import asyncio
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestSessionEngineOptions(unittest.TestCase):
    def reload_session(self, database_url: str, engine_calls: list[dict] | None = None):
        for name in ["db.session", "db"]:
            sys.modules.pop(name, None)
        patches = [patch.dict(os.environ, {"DATABASE_URL": database_url}, clear=False)]
        if engine_calls is not None:
            class FakeEngine:
                class FakePool:
                    pass

                pool = FakePool()

                async def dispose(self):
                    return None

            def fake_create_async_engine(url, **kwargs):
                engine_calls.append({"url": url, "kwargs": kwargs})
                return FakeEngine()

            patches.append(
                patch("sqlalchemy.ext.asyncio.create_async_engine", side_effect=fake_create_async_engine)
            )

        exits = []
        try:
            for patcher in patches:
                exits.append(patcher.__enter__())
            return importlib.import_module("db.session")
        finally:
            for patcher in reversed(patches):
                patcher.__exit__(None, None, None)

    def test_postgresql_uses_null_pool(self):
        engine_calls: list[dict] = []
        session = self.reload_session(
            "postgresql+asyncpg://user:pass@localhost/db",
            engine_calls=engine_calls,
        )

        self.assertEqual(
            session.SYNC_DATABASE_URL,
            "postgresql+psycopg2://user:pass@localhost/db",
        )
        self.assertEqual(engine_calls[0]["url"], "postgresql+asyncpg://user:pass@localhost/db")
        self.assertEqual(engine_calls[0]["kwargs"]["poolclass"].__name__, "NullPool")

    def test_sqlite_keeps_non_null_pool_behavior(self):
        session = self.reload_session("sqlite+aiosqlite:///tmp/test-session.sqlite")
        try:
            self.assertNotEqual(session.engine.pool.__class__.__name__, "NullPool")
            self.assertEqual(session.SYNC_DATABASE_URL, "sqlite:///tmp/test-session.sqlite")
        finally:
            asyncio.run(session.engine.dispose())
