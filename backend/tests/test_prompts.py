from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-prompts-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_prompts.sqlite"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["DEPLOY_SECRET"] = "test-deploy-secret"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "30"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from auth.security import hash_password  # noqa: E402
from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import PromptTemplate, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import prompts as prompts_router  # noqa: E402


class PromptRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_app = FastAPI()
        test_app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        test_app.include_router(prompts_router.router, prefix="/api/prompts", tags=["Prompts"])
        cls.client = TestClient(test_app)
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)

    def register(self, username: str, password: str) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "email": f"{username}@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def create_admin(self, username: str = "admin", password: str = "pwd12345") -> None:
        with Session(self.sync_engine) as session:
            admin = User(
                username=username,
                email=f"{username}@example.com",
                password_hash=hash_password(password),
                role="admin",
                is_active=1,
                token_version=0,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(admin)
            session.commit()

    def login_headers(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_catalog_seeds_builtin_system_prompts(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        response = self.client.get("/api/prompts/catalog", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["types"])

        with Session(self.sync_engine) as session:
            seeded = session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.scope == "system",
                    PromptTemplate.owner_user_id.is_(None),
                )
            ).scalars().all()
        self.assertTrue(seeded)

    def test_user_override_has_priority_and_can_be_reset(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        initial = self.client.get(
            "/api/prompts/item",
            headers=headers,
            params={"type": "long", "key": "overview"},
        )
        self.assertEqual(initial.status_code, 200, initial.text)
        initial_data = initial.json()
        self.assertEqual(initial_data["source"], "system_default")
        self.assertTrue(initial_data["system_content"])

        save = self.client.put(
            "/api/prompts/my",
            headers=headers,
            json={"type": "long", "key": "overview", "content": "我的研究问题提示词"},
        )
        self.assertEqual(save.status_code, 200, save.text)

        overridden = self.client.get(
            "/api/prompts/item",
            headers=headers,
            params={"type": "long", "key": "overview"},
        )
        self.assertEqual(overridden.status_code, 200, overridden.text)
        overridden_data = overridden.json()
        self.assertEqual(overridden_data["source"], "user_override")
        self.assertEqual(overridden_data["effective_content"], "我的研究问题提示词")
        self.assertTrue(overridden_data["has_user_override"])

        reset = self.client.delete(
            "/api/prompts/my",
            headers=headers,
            params={"type": "long", "key": "overview"},
        )
        self.assertEqual(reset.status_code, 200, reset.text)

        restored = self.client.get(
            "/api/prompts/item",
            headers=headers,
            params={"type": "long", "key": "overview"},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        restored_data = restored.json()
        self.assertEqual(restored_data["source"], "system_default")
        self.assertEqual(restored_data["effective_content"], initial_data["system_content"])

    def test_normal_user_cannot_update_system_prompt(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        response = self.client.put(
            "/api/prompts/system",
            headers=headers,
            json={"type": "filter", "key": "explorer", "content": "forbidden"},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_admin_can_update_system_prompt_for_all_users(self) -> None:
        self.create_admin()
        self.register("alice", "pwd12345")
        admin_headers = self.login_headers("admin", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")

        update = self.client.put(
            "/api/prompts/system",
            headers=admin_headers,
            json={"type": "filter", "key": "explorer", "content": "管理员系统默认提示词"},
        )
        self.assertEqual(update.status_code, 200, update.text)

        read_back = self.client.get(
            "/api/prompts/item",
            headers=alice_headers,
            params={"type": "filter", "key": "explorer"},
        )
        self.assertEqual(read_back.status_code, 200, read_back.text)
        data = read_back.json()
        self.assertEqual(data["source"], "system_default")
        self.assertEqual(data["effective_content"], "管理员系统默认提示词")
