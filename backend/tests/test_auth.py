from __future__ import annotations

import os
import sys
import tempfile
import unittest
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jose import jwt
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-auth-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_auth.sqlite"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["DEPLOY_SECRET"] = "test-deploy-secret"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "30"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from auth.security import get_jwt_algorithm, get_jwt_secret_key  # noqa: E402
from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import InviteCode, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402


class AuthRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_app = FastAPI()
        test_app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
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

    def create_admin(self) -> int:
        with Session(self.sync_engine) as session:
            existing = session.execute(
                select(User).where(User.username == "admin")
            ).scalar_one_or_none()
            if existing is not None:
                return existing.id
            admin = User(
                username="admin",
                email="admin@example.com",
                password_hash="hashed",
                role="admin",
                is_active=1,
                token_version=0,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(admin)
            session.commit()
            session.refresh(admin)
            return admin.id

    def create_invite(
        self,
        code: str,
        *,
        expires_at: datetime | None = None,
        max_uses: int = 1,
        used_count: int = 0,
    ) -> None:
        admin_id = self.create_admin()
        with Session(self.sync_engine) as session:
            invite = InviteCode(
                code=code,
                created_by_user_id=admin_id,
                max_uses=max_uses,
                used_count=used_count,
                expires_at=expires_at,
            )
            session.add(invite)
            session.commit()

    def login(self, username: str, password: str) -> dict:
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_register_and_me_for_normal_user(self) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pwd12345"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["user"]["role"], "normal")
        self.assertIn("24 小时", data["user"]["warning_msg"])

        tokens = self.login("alice", "pwd12345")
        me = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["username"], "alice")

    def test_duplicate_username_is_rejected(self) -> None:
        payload = {"username": "alice", "password": "pwd12345"}
        first = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(first.status_code, 200, first.text)

        second = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(second.status_code, 400, second.text)
        self.assertIn("用户名已存在", second.json()["detail"])

    def test_invite_code_validation(self) -> None:
        self.create_invite("VIP-OK")
        valid = self.client.post(
            "/api/auth/register",
            json={"username": "vipuser", "password": "pwd12345", "invite_code": "VIP-OK"},
        )
        self.assertEqual(valid.status_code, 200, valid.text)
        self.assertEqual(valid.json()["user"]["role"], "vip")

        expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        self.create_invite("VIP-EXPIRED", expires_at=expired_at)
        expired = self.client.post(
            "/api/auth/register",
            json={"username": "expired", "password": "pwd12345", "invite_code": "VIP-EXPIRED"},
        )
        self.assertEqual(expired.status_code, 400, expired.text)
        self.assertIn("已过期", expired.json()["detail"])

        self.create_invite("VIP-USED", max_uses=1, used_count=1)
        used = self.client.post(
            "/api/auth/register",
            json={"username": "usedup", "password": "pwd12345", "invite_code": "VIP-USED"},
        )
        self.assertEqual(used.status_code, 400, used.text)
        self.assertIn("已使用完毕", used.json()["detail"])

        missing = self.client.post(
            "/api/auth/register",
            json={"username": "missing", "password": "pwd12345", "invite_code": "NOPE"},
        )
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertIn("邀请码无效", missing.json()["detail"])

    def test_login_and_invalid_credentials(self) -> None:
        self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pwd12345"},
        )

        ok = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "pwd12345"},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        tokens = ok.json()
        self.assertIn("access_token", tokens)
        self.assertIn("refresh_token", tokens)

        wrong_password = self.client.post(
            "/api/auth/login",
            data={"username": "alice", "password": "wrongpass1"},
        )
        self.assertEqual(wrong_password.status_code, 401, wrong_password.text)

        missing_user = self.client.post(
            "/api/auth/login",
            data={"username": "nobody", "password": "pwd12345"},
        )
        self.assertEqual(missing_user.status_code, 401, missing_user.text)

    def test_tampered_and_expired_access_token_return_401(self) -> None:
        self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pwd12345"},
        )
        tokens = self.login("alice", "pwd12345")

        tampered = tokens["access_token"][:-1] + ("a" if tokens["access_token"][-1] != "a" else "b")
        tampered_response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {tampered}"},
        )
        self.assertEqual(tampered_response.status_code, 401, tampered_response.text)

        expired_token = jwt.encode(
            {
                "sub": "1",
                "type": "access",
                "iat": int((datetime.now(UTC) - timedelta(minutes=2)).timestamp()),
                "exp": int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
            },
            get_jwt_secret_key(),
            algorithm=get_jwt_algorithm(),
        )
        expired_response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(expired_response.status_code, 401, expired_response.text)

    def test_logout_revokes_old_refresh_token(self) -> None:
        self.client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pwd12345"},
        )
        tokens = self.login("alice", "pwd12345")

        refresh_before_logout = self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        self.assertEqual(refresh_before_logout.status_code, 200, refresh_before_logout.text)

        logout = self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        self.assertEqual(logout.status_code, 200, logout.text)

        refresh_after_logout = self.client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        self.assertEqual(refresh_after_logout.status_code, 401, refresh_after_logout.text)


if __name__ == "__main__":
    unittest.main()
