from __future__ import annotations

import asyncio
import os
import shutil
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

TEMP_DIR = tempfile.mkdtemp(prefix="dra-upload-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_upload.sqlite"
TEST_UPLOAD_ROOT = Path(TEMP_DIR) / "uploads"

os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}")
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ["UPLOAD_ROOT_DIR"] = TEST_UPLOAD_ROOT.as_posix()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from auth.security import hash_password  # noqa: E402
from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import File, InviteCode, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import upload as upload_router  # noqa: E402


class UploadRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        test_app = FastAPI()
        test_app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        test_app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload"])
        cls.client = TestClient(test_app)
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    def create_user(self, username: str, password: str, *, role: str = "normal") -> int:
        with Session(self.sync_engine) as session:
            user = User(
                username=username,
                email=f"{username}@example.com",
                password_hash=hash_password(password),
                role=role,
                is_active=1,
                token_version=0,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user.id

    def create_invite(self, code: str) -> None:
        admin_id = self.create_user("admin", "admin12345", role="admin")
        with Session(self.sync_engine) as session:
            invite = InviteCode(code=code, created_by_user_id=admin_id, max_uses=1, used_count=0)
            session.add(invite)
            session.commit()

    def register(self, username: str, password: str, *, invite_code: str | None = None) -> None:
        payload = {"username": username, "password": password}
        if invite_code:
            payload["invite_code"] = invite_code
        response = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(response.status_code, 200, response.text)

    def login_headers(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def upload_pdf(self, headers: dict[str, str], *, filename: str = "paper.pdf", content: bytes | None = None):
        response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": (filename, content or b"%PDF-1.4 test pdf", "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_upload_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/upload/",
            files={"file": ("paper.pdf", b"%PDF-1.4 test pdf", "application/pdf")},
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_normal_user_upload_creates_record_with_expiry(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        payload = self.upload_pdf(headers)

        self.assertTrue(payload["success"])
        self.assertEqual(payload["type"], "pdf")
        self.assertIsNotNone(payload["expires_at"])
        self.assertFalse(payload["deduplicated"])
        self.assertIn("/1/", payload["storage_path"])

        stored_path = Path(payload["storage_path"])
        if not stored_path.is_absolute():
            stored_path = PROJECT_ROOT / stored_path
        self.assertTrue(stored_path.exists())

        with Session(self.sync_engine) as session:
            record = session.execute(select(File).where(File.id == payload["file_id"])).scalar_one()
            self.assertEqual(record.owner_user_id, 1)
            self.assertIsNotNone(record.expires_at)

    def test_vip_and_admin_uploads_do_not_expire(self) -> None:
        self.create_invite("VIP-OK")
        self.register("vipuser", "pwd12345", invite_code="VIP-OK")
        vip_headers = self.login_headers("vipuser", "pwd12345")
        vip_payload = self.upload_pdf(vip_headers, filename="vip-paper.pdf")
        self.assertIsNone(vip_payload["expires_at"])

        self.create_user("rootadmin", "pwd12345", role="admin")
        admin_headers = self.login_headers("rootadmin", "pwd12345")
        admin_payload = self.upload_pdf(admin_headers, filename="admin-paper.pdf")
        self.assertIsNone(admin_payload["expires_at"])

    def test_same_user_same_md5_returns_existing_record(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        first = self.upload_pdf(headers, content=b"%PDF-1.4 same content")
        second = self.upload_pdf(headers, filename="same-name.pdf", content=b"%PDF-1.4 same content")

        self.assertEqual(first["file_id"], second["file_id"])
        self.assertTrue(second["deduplicated"])

        with Session(self.sync_engine) as session:
            count = session.query(File).count()
            self.assertEqual(count, 1)

    def test_different_users_same_md5_create_separate_records(self) -> None:
        self.register("alice", "pwd12345")
        self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")

        alice_payload = self.upload_pdf(alice_headers, content=b"%PDF-1.4 shared content")
        bob_payload = self.upload_pdf(bob_headers, content=b"%PDF-1.4 shared content")

        self.assertNotEqual(alice_payload["file_id"], bob_payload["file_id"])
        self.assertNotEqual(alice_payload["storage_path"], bob_payload["storage_path"])

        with Session(self.sync_engine) as session:
            records = session.execute(select(File).order_by(File.owner_user_id)).scalars().all()
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0].md5, records[1].md5)
            self.assertNotEqual(records[0].owner_user_id, records[1].owner_user_id)

    def test_upload_info_only_visible_to_owner(self) -> None:
        self.register("alice", "pwd12345")
        self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")

        payload = self.upload_pdf(alice_headers)

        own_info = self.client.get(f"/api/upload/{payload['file_id']}/info", headers=alice_headers)
        self.assertEqual(own_info.status_code, 200, own_info.text)

        other_info = self.client.get(f"/api/upload/{payload['file_id']}/info", headers=bob_headers)
        self.assertEqual(other_info.status_code, 404, other_info.text)

    def test_rejects_unsupported_extension(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": ("malware.exe", b"not allowed", "application/octet-stream")},
        )
        self.assertEqual(response.status_code, 400, response.text)

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(File).count(), 0)

    def test_supports_docx_txt_and_bibliography_detection(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")

        docx_response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={
                "file": (
                    "notes.docx",
                    b"PK\x03\x04 minimal docx payload",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        self.assertEqual(docx_response.status_code, 200, docx_response.text)
        self.assertEqual(docx_response.json()["type"], "docx")

        txt_response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": ("plain.txt", b"just some plain text", "text/plain")},
        )
        self.assertEqual(txt_response.status_code, 200, txt_response.text)
        self.assertEqual(txt_response.json()["type"], "txt")

        bib_response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": ("wos.txt", b"FN Clarivate Analytics Web of Science\nAU Smith", "text/plain")},
        )
        self.assertEqual(bib_response.status_code, 200, bib_response.text)
        self.assertEqual(bib_response.json()["type"], "bibliography")


if __name__ == "__main__":
    unittest.main()
