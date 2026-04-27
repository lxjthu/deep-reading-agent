from __future__ import annotations

import asyncio
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

TEMP_DIR = tempfile.mkdtemp(prefix="dra-history-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_history.sqlite"
TEST_RESULTS_ROOT = Path(TEMP_DIR) / "results"
TEST_UPLOAD_ROOT = Path(TEMP_DIR) / "uploads"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")
os.environ["UPLOAD_ROOT_DIR"] = TEST_UPLOAD_ROOT.as_posix()

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import Artifact, Job, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import download as download_router  # noqa: E402
from routers import history as history_router  # noqa: E402


class HistoryRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        history_router.RESULTS_DIR = TEST_RESULTS_ROOT.as_posix()
        history_router.FILTER_DIR = (TEST_RESULTS_ROOT / "literature_filter").as_posix()
        history_router.SYNTHESIS_DIR = (TEST_RESULTS_ROOT / "synthesis").as_posix()
        Path(history_router.SYNTHESIS_DIR).mkdir(parents=True, exist_ok=True)
        download_router.RESULTS_DIR = TEST_RESULTS_ROOT.as_posix()

        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        app.include_router(history_router.router, prefix="/api/history", tags=["History"])
        app.include_router(download_router.router, prefix="/api/download", tags=["Download"])
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
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        Path(history_router.SYNTHESIS_DIR).mkdir(parents=True, exist_ok=True)

    def register(self, username: str, password: str = "pwd12345") -> int:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "email": f"{username}@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.sync_engine) as session:
            user = session.execute(select(User).where(User.username == username)).scalar_one()
            return user.id

    def promote_to_admin(self, username: str) -> None:
        with Session(self.sync_engine) as session:
            user = session.execute(select(User).where(User.username == username)).scalar_one()
            user.role = "admin"
            session.commit()

    def login_headers(self, username: str, password: str = "pwd12345") -> dict[str, str]:
        response = self.client.post("/api/auth/login", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_artifact(
        self,
        owner_user_id: int,
        *,
        job_type: str,
        artifact_type: str,
        filename: str,
        content: bytes,
    ) -> tuple[str, str]:
        job_id = str(uuid.uuid4())
        storage_path = f"{owner_user_id}/{job_id}/{filename}"
        absolute_path = TEST_RESULTS_ROOT / storage_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(content)

        with Session(self.sync_engine) as session:
            session.add(
                Job(
                    id=job_id,
                    owner_user_id=owner_user_id,
                    job_type=job_type,
                    status="success",
                    params_json="{}",
                    progress=100,
                    current_stage="完成",
                )
            )
            session.add(
                Artifact(
                    job_id=job_id,
                    owner_user_id=owner_user_id,
                    artifact_type=artifact_type,
                    filename=filename,
                    storage_path=storage_path,
                    size_bytes=len(content),
                )
            )
            session.commit()
        return job_id, storage_path

    def test_history_list_requires_authentication(self) -> None:
        response = self.client.get("/api/history/")
        self.assertEqual(response.status_code, 401, response.text)

    def test_history_list_only_returns_current_user_artifacts(self) -> None:
        alice_id = self.register("alice")
        bob_id = self.register("bob")
        alice_headers = self.login_headers("alice")

        self.create_artifact(
            alice_id,
            job_type="reading_quant",
            artifact_type="reading_final",
            filename="alice_7step.md",
            content=b"# alice",
        )
        self.create_artifact(
            alice_id,
            job_type="filter",
            artifact_type="filter_excel",
            filename="alice_filter.xlsx",
            content=b"excel",
        )
        self.create_artifact(
            bob_id,
            job_type="reading_long",
            artifact_type="reading_final",
            filename="bob_long.md",
            content=b"# bob",
        )

        response = self.client.get("/api/history/", headers=alice_headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual({item["filename"] for item in body["reading"]}, {"alice_7step.md"})
        self.assertEqual({item["filename"] for item in body["filter"]}, {"alice_filter.xlsx"})
        self.assertEqual({item["filename"] for item in body["all"]}, {"alice_7step.md", "alice_filter.xlsx"})

    def test_admin_history_list_can_target_owner_user_id(self) -> None:
        alice_id = self.register("alice")
        self.register("admin_user")
        self.promote_to_admin("admin_user")
        admin_headers = self.login_headers("admin_user")

        self.create_artifact(
            alice_id,
            job_type="reading_qual",
            artifact_type="reading_final",
            filename="alice_4step.md",
            content=b"# alice",
        )

        response = self.client.get(f"/api/history/?owner_user_id={alice_id}", headers=admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["filename"] for item in response.json()["all"]], ["alice_4step.md"])

    def test_history_preview_requires_owner(self) -> None:
        alice_id = self.register("alice")
        bob_id = self.register("bob")
        alice_headers = self.login_headers("alice")
        self.create_artifact(
            bob_id,
            job_type="reading_long",
            artifact_type="reading_final",
            filename="bob_report.md",
            content=b"# Bob Report",
        )

        response = self.client.get("/api/history/bob_report.md/preview", headers=alice_headers)
        self.assertEqual(response.status_code, 404, response.text)

    def test_history_delete_requires_owner(self) -> None:
        alice_id = self.register("alice")
        bob_id = self.register("bob")
        alice_headers = self.login_headers("alice")
        _job_id, storage_path = self.create_artifact(
            bob_id,
            job_type="reading_long",
            artifact_type="reading_final",
            filename="bob_report.md",
            content=b"# Bob Report",
        )

        response = self.client.delete("/api/history/bob_report.md", headers=alice_headers)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertTrue((TEST_RESULTS_ROOT / storage_path).exists())
        with Session(self.sync_engine) as session:
            artifact = session.execute(select(Artifact).where(Artifact.storage_path == storage_path)).scalar_one_or_none()
            self.assertIsNotNone(artifact)

    def test_history_delete_removes_artifact_record_and_file(self) -> None:
        alice_id = self.register("alice")
        alice_headers = self.login_headers("alice")
        _job_id, storage_path = self.create_artifact(
            alice_id,
            job_type="reading_quant",
            artifact_type="reading_step",
            filename="step_1.md",
            content=b"# Step 1",
        )

        response = self.client.delete("/api/history/step_1.md", headers=alice_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse((TEST_RESULTS_ROOT / storage_path).exists())
        with Session(self.sync_engine) as session:
            artifact = session.execute(select(Artifact).where(Artifact.storage_path == storage_path)).scalar_one_or_none()
            self.assertIsNone(artifact)

    def test_download_requires_authentication(self) -> None:
        response = self.client.get("/api/download/some_file.md")
        self.assertEqual(response.status_code, 401, response.text)

    def test_download_rejects_non_owned_artifact(self) -> None:
        alice_id = self.register("alice")
        bob_id = self.register("bob")
        alice_headers = self.login_headers("alice")
        _job_id, storage_path = self.create_artifact(
            bob_id,
            job_type="reading_long",
            artifact_type="reading_final",
            filename="bob_report.md",
            content=b"# Bob Report",
        )

        response = self.client.get(f"/api/download/{storage_path}", headers=alice_headers)
        self.assertEqual(response.status_code, 404, response.text)

    def test_download_accepts_storage_path_for_owner(self) -> None:
        alice_id = self.register("alice")
        alice_headers = self.login_headers("alice")
        _job_id, storage_path = self.create_artifact(
            alice_id,
            job_type="reading_long",
            artifact_type="reading_final",
            filename="alice_report.md",
            content=b"# Alice Report",
        )

        response = self.client.get(f"/api/download/{storage_path}", headers=alice_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"# Alice Report")

    def test_download_accepts_filename_for_owner(self) -> None:
        alice_id = self.register("alice")
        alice_headers = self.login_headers("alice")
        self.create_artifact(
            alice_id,
            job_type="filter",
            artifact_type="filter_excel",
            filename="alice_filter.xlsx",
            content=b"excel-data",
        )

        response = self.client.get("/api/download/alice_filter.xlsx", headers=alice_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"excel-data")

    def test_admin_can_download_other_users_artifact(self) -> None:
        alice_id = self.register("alice")
        self.register("admin_user")
        self.promote_to_admin("admin_user")
        admin_headers = self.login_headers("admin_user")
        _job_id, storage_path = self.create_artifact(
            alice_id,
            job_type="reading_long",
            artifact_type="reading_final",
            filename="alice_report.md",
            content=b"# Alice Report",
        )

        response = self.client.get(f"/api/download/{storage_path}", headers=admin_headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"# Alice Report")


if __name__ == "__main__":
    unittest.main()
