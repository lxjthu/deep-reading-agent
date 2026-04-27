from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-admin-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_admin.sqlite"

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
from db.models import Artifact, BibEntry, File, InviteCode, Job, UploadBatch, User  # noqa: E402
from routers import admin as admin_router  # noqa: E402
from routers import auth as auth_router  # noqa: E402


class AdminRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        app.include_router(admin_router.router, prefix="/api/admin", tags=["Admin"])
        cls.client = TestClient(app)
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)

    def create_user(self, username: str, password: str, *, role: str = "normal", is_active: int = 1) -> int:
        with Session(self.sync_engine) as session:
            user = User(
                username=username,
                email=f"{username}@example.com",
                password_hash=hash_password(password),
                role=role,
                is_active=is_active,
                token_version=0,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user.id

    def login_headers(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post("/api/auth/login", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_invite(self, code: str) -> int:
        admin_id = self.create_user("seedadmin", "pwd12345", role="admin")
        with Session(self.sync_engine) as session:
            invite = InviteCode(
                code=code,
                created_by_user_id=admin_id,
                max_uses=1,
                used_count=0,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(invite)
            session.commit()
            session.refresh(invite)
            return invite.id

    def create_owned_records(self, owner_user_id: int, *, expires_at: datetime | None) -> None:
        job_id = str(uuid.uuid4())
        file_id = str(uuid.uuid4())
        with Session(self.sync_engine) as session:
            session.add(
                UploadBatch(
                    id=str(uuid.uuid4()),
                    owner_user_id=owner_user_id,
                    source_type="single",
                    total_files=1,
                    succeeded=1,
                    failed=0,
                    status="success",
                    expires_at=expires_at,
                )
            )
            session.add(
                File(
                    id=file_id,
                    owner_user_id=owner_user_id,
                    batch_id=None,
                    file_type="pdf",
                    original_name="paper.pdf",
                    storage_path=f"_uploads/{owner_user_id}/{file_id}.pdf",
                    size_bytes=10,
                    md5=f"md5-{owner_user_id}",
                    expires_at=expires_at,
                )
            )
            session.add(
                Job(
                    id=job_id,
                    owner_user_id=owner_user_id,
                    job_type="reading_long",
                    status="success",
                    input_file_id=file_id,
                    params_json="{}",
                    progress=100,
                    current_stage="完成",
                    expires_at=expires_at,
                )
            )
            session.add(
                BibEntry(
                    id=str(uuid.uuid4()),
                    owner_user_id=owner_user_id,
                    title="Sample Paper",
                    authors_json='["Alice"]',
                    source_db="manual",
                    reading_status="read",
                    dedup_key=f"dedup-{owner_user_id}",
                    source_file_id=file_id,
                    source_filter_job_id=None,
                    metadata_completeness="full",
                    expires_at=expires_at,
                )
            )
            session.add(
                Artifact(
                    job_id=job_id,
                    owner_user_id=owner_user_id,
                    artifact_type="reading_final",
                    filename="final.md",
                    storage_path=f"{owner_user_id}/{job_id}/final.md",
                    size_bytes=20,
                    expires_at=expires_at,
                )
            )
            session.commit()

    def test_admin_routes_require_admin_role(self) -> None:
        self.create_user("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        users = self.client.get("/api/admin/users", headers=headers)
        self.assertEqual(users.status_code, 403, users.text)

        invites = self.client.post("/api/admin/invite_codes", headers=headers, json={"code": "VIP-NOPE"})
        self.assertEqual(invites.status_code, 403, invites.text)

    def test_admin_can_list_users_and_invite_codes(self) -> None:
        self.create_user("rootadmin", "pwd12345", role="admin")
        self.create_user("alice", "pwd12345")
        self.create_invite("VIP-ONE")
        headers = self.login_headers("rootadmin", "pwd12345")

        users = self.client.get("/api/admin/users", headers=headers)
        self.assertEqual(users.status_code, 200, users.text)
        usernames = {item["username"] for item in users.json()}
        self.assertIn("rootadmin", usernames)
        self.assertIn("alice", usernames)

        invites = self.client.get("/api/admin/invite_codes", headers=headers)
        self.assertEqual(invites.status_code, 200, invites.text)
        self.assertEqual(invites.json()[0]["code"], "VIP-ONE")

    def test_admin_can_create_and_revoke_invite_code(self) -> None:
        self.create_user("rootadmin", "pwd12345", role="admin")
        headers = self.login_headers("rootadmin", "pwd12345")

        created = self.client.post(
            "/api/admin/invite_codes",
            headers=headers,
            json={"code": "VIP-CREATE", "max_uses": 2, "note": "for vip"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        invite_id = created.json()["id"]

        register = self.client.post(
            "/api/auth/register",
            json={"username": "vipuser", "password": "pwd12345", "invite_code": "VIP-CREATE"},
        )
        self.assertEqual(register.status_code, 200, register.text)
        self.assertEqual(register.json()["user"]["role"], "vip")

        deleted = self.client.delete(f"/api/admin/invite_codes/{invite_id}", headers=headers)
        self.assertEqual(deleted.status_code, 200, deleted.text)

        missing = self.client.post(
            "/api/auth/register",
            json={"username": "othervip", "password": "pwd12345", "invite_code": "VIP-CREATE"},
        )
        self.assertEqual(missing.status_code, 400, missing.text)
        self.assertIn("邀请码无效", missing.json()["detail"])

    def test_admin_role_upgrade_clears_existing_expires_at(self) -> None:
        self.create_user("rootadmin", "pwd12345", role="admin")
        alice_id = self.create_user("alice", "pwd12345", role="normal")
        self.create_owned_records(alice_id, expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2))
        headers = self.login_headers("rootadmin", "pwd12345")

        response = self.client.patch(f"/api/admin/users/{alice_id}", headers=headers, json={"role": "vip"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["role"], "vip")

        with Session(self.sync_engine) as session:
            self.assertIsNone(session.execute(select(File.expires_at).where(File.owner_user_id == alice_id)).scalar_one())
            self.assertIsNone(session.execute(select(BibEntry.expires_at).where(BibEntry.owner_user_id == alice_id)).scalar_one())
            self.assertIsNone(session.execute(select(Job.expires_at).where(Job.owner_user_id == alice_id)).scalar_one())
            self.assertIsNone(session.execute(select(Artifact.expires_at).where(Artifact.owner_user_id == alice_id)).scalar_one())
            self.assertIsNone(session.execute(select(UploadBatch.expires_at).where(UploadBatch.owner_user_id == alice_id)).scalar_one())

    def test_admin_role_downgrade_sets_expires_at_for_existing_data(self) -> None:
        self.create_user("rootadmin", "pwd12345", role="admin")
        alice_id = self.create_user("alice", "pwd12345", role="vip")
        self.create_owned_records(alice_id, expires_at=None)
        headers = self.login_headers("rootadmin", "pwd12345")

        started_at = datetime.now(UTC).replace(tzinfo=None)
        response = self.client.patch(f"/api/admin/users/{alice_id}", headers=headers, json={"role": "normal"})
        self.assertEqual(response.status_code, 200, response.text)

        with Session(self.sync_engine) as session:
            file_expires = session.execute(select(File.expires_at).where(File.owner_user_id == alice_id)).scalar_one()
            self.assertIsNotNone(file_expires)
            self.assertGreaterEqual(file_expires, started_at + timedelta(hours=23, minutes=59))
            self.assertLessEqual(file_expires, started_at + timedelta(hours=24, minutes=1))

    def test_admin_can_reset_password_and_toggle_active(self) -> None:
        self.create_user("rootadmin", "pwd12345", role="admin")
        alice_id = self.create_user("alice", "pwd12345", role="normal")
        headers = self.login_headers("rootadmin", "pwd12345")

        reset = self.client.patch(
            f"/api/admin/users/{alice_id}",
            headers=headers,
            json={"new_password": "newpwd123", "is_active": 0},
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(reset.json()["user"]["is_active"], 0)

        old_login = self.client.post("/api/auth/login", data={"username": "alice", "password": "pwd12345"})
        self.assertEqual(old_login.status_code, 401, old_login.text)

        disabled_login = self.client.post("/api/auth/login", data={"username": "alice", "password": "newpwd123"})
        self.assertEqual(disabled_login.status_code, 403, disabled_login.text)

        enable = self.client.patch(
            f"/api/admin/users/{alice_id}",
            headers=headers,
            json={"is_active": 1},
        )
        self.assertEqual(enable.status_code, 200, enable.text)

        new_login = self.client.post("/api/auth/login", data={"username": "alice", "password": "newpwd123"})
        self.assertEqual(new_login.status_code, 200, new_login.text)


if __name__ == "__main__":
    unittest.main()
