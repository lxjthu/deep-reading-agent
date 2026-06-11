from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-translation-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_translation.sqlite"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["UPLOAD_ROOT_DIR"] = str((Path(TEMP_DIR) / "_uploads").resolve())
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import BibEntry, File, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import translation as translation_router  # noqa: E402
from upload_storage import build_storage_path  # noqa: E402


class TranslationRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        app.include_router(translation_router.router, prefix="/api/translation", tags=["Translation"])
        cls.client = TestClient(app)
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

    def register(self, username: str, password: str = "pwd12345") -> int:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "email": f"{username}@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.sync_engine) as session:
            user = session.execute(select(User).where(User.username == username)).scalar_one()
            return user.id

    def login_headers(self, username: str, password: str = "pwd12345") -> dict[str, str]:
        response = self.client.post("/api/auth/login", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_english_entry(self, owner_user_id: int, *, file_exists: bool) -> tuple[str, str]:
        file_id = str(uuid.uuid4())
        bib_id = str(uuid.uuid4())
        file_path, storage_path = build_storage_path(owner_user_id, file_id, ".pdf")
        if file_exists:
            file_path.write_bytes(b"%PDF-1.4 translation source")
        with Session(self.sync_engine) as session:
            session.add(
                File(
                    id=file_id,
                    owner_user_id=owner_user_id,
                    original_name="sample.pdf",
                    file_type="pdf",
                    storage_path=storage_path,
                    size_bytes=128,
                    md5=f"md5-{owner_user_id}-{file_id}",
                    batch_id=None,
                )
            )
            session.add(
                BibEntry(
                    id=bib_id,
                    owner_user_id=owner_user_id,
                    title="Sample English Paper",
                    authors_json=json.dumps(["Alice"], ensure_ascii=False),
                    year=2024,
                    doi="10.1000/translation",
                    journal="Journal of Translation",
                    source_db="manual",
                    source_filter_job_id=None,
                    source_file_id=file_id,
                    user_tags_json="[]",
                    user_note=None,
                    is_pinned=0,
                    reading_status="has_pdf",
                    metadata_completeness="partial",
                    language="en",
                    dedup_key="title:sample-english-paper",
                )
            )
            session.commit()
        return bib_id, file_id

    def test_translatable_skips_missing_source_files_and_clears_link(self) -> None:
        alice_id = self.register("alice")
        bib_id, _file_id = self.create_english_entry(alice_id, file_exists=False)

        response = self.client.get("/api/translation/translatable", headers=self.login_headers("alice"))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"entries": []})

        with Session(self.sync_engine) as session:
            entry = session.execute(select(BibEntry).where(BibEntry.id == bib_id)).scalar_one()
            self.assertIsNone(entry.source_file_id)

    def test_start_translation_rejects_missing_source_file(self) -> None:
        alice_id = self.register("alice")
        bib_id, file_id = self.create_english_entry(alice_id, file_exists=False)

        response = self.client.post(
            "/api/translation/start",
            headers=self.login_headers("alice"),
            json={"file_id": file_id, "bib_entry_id": bib_id, "api_key": "sk-test", "max_workers": 1},
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertIn("源文件已丢失", response.json()["detail"])

        with Session(self.sync_engine) as session:
            entry = session.execute(select(BibEntry).where(BibEntry.id == bib_id)).scalar_one()
            self.assertIsNone(entry.source_file_id)


if __name__ == "__main__":
    unittest.main()
