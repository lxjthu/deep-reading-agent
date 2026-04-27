from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-filter-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_filter.sqlite"
TEST_UPLOAD_ROOT = Path(TEMP_DIR) / "uploads"
TEST_RESULTS_ROOT = Path(TEMP_DIR) / "results"

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
from db.models import Artifact, BibEntry, BibFilterLink, File, Job, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import filter as filter_router  # noqa: E402
from routers import upload as upload_router  # noqa: E402


WOS_SAMPLE = b"""FN Clarivate Analytics Web of Science
VR 1.0
PT J
AU Smith, John
TI Causal effect of policy on outcomes
SO Journal of Policy
PY 2024
AB This abstract discusses treatment effects.
DI 10.1000/exampledoi
ER
PT J
AU Smith, John
TI Causal effect of policy on outcomes
SO Journal of Policy
PY 2024
AB Duplicate row in same file
DI 10.1000/exampledoi
ER
"""


PENDING_FILTER_RUNS: list[tuple[tuple, dict]] = []


def run_pending_filter_tasks():
    pending = list(PENDING_FILTER_RUNS)
    PENDING_FILTER_RUNS.clear()
    for args, kwargs in pending:
        FilterRouterTests._original_run_filter_task(*args, **kwargs)


class FakePromptManager:
    @staticmethod
    def load_prompt(mode):
        return f"prompt:{mode}"


class FakeAIEvaluator:
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key
        self.model = model

    def evaluate_batch(self, df, prompt_template, topic):
        return [
            {
                "original_index": index,
                "score": 95.0 - idx,
                "reason": f"matched:{topic}",
            }
            for idx, index in enumerate(df.index.tolist())
        ]


def fake_filter_literature(df, min_year=None, keywords=None):
    if min_year and min_year >= 2030:
        return df.iloc[0:0].copy()
    return df.copy()


class FilterRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        filter_router.RESULTS_ROOT = TEST_RESULTS_ROOT
        filter_router.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        cls._original_run_filter_task = filter_router.run_filter_task

        cls._patchers = [
            patch.object(
                filter_router,
                "run_filter_task",
                lambda *args, **kwargs: PENDING_FILTER_RUNS.append((args, kwargs)),
            ),
            patch.dict(
                sys.modules,
                {
                    "smart_literature_filter": types.SimpleNamespace(
                        filter_literature=fake_filter_literature,
                        AIEvaluator=FakeAIEvaluator,
                        PromptManager=FakePromptManager,
                    )
                },
            ),
        ]
        for patcher in cls._patchers:
            patcher.start()

        test_app = FastAPI()
        test_app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        test_app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload"])
        test_app.include_router(filter_router.router, prefix="/api/filter", tags=["Filter"])
        cls.client = TestClient(test_app)
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())
        for patcher in reversed(cls._patchers):
            patcher.stop()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        filter_router.tasks.clear()
        PENDING_FILTER_RUNS.clear()

    def register(self, username: str, password: str, *, invite_code: str | None = None) -> None:
        payload = {"username": username, "password": password, "email": f"{username}@example.com"}
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
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def upload_bibliography(self, headers: dict[str, str], *, filename: str = "savedrecs.txt") -> dict:
        response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": (filename, WOS_SAMPLE, "text/plain")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def start_filter(self, headers: dict[str, str], file_id: str, *, topic: str = "policy", min_year: int = 2020):
        response = self.client.post(
            "/api/filter/start",
            headers=headers,
            json={
                "file_id": file_id,
                "mode": "explorer",
                "topic": topic,
                "min_year": min_year,
                "api_key": "dummy-key",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        run_pending_filter_tasks()
        return response.json()

    def test_filter_start_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/filter/start",
            json={"file_id": "missing", "mode": "explorer", "topic": "policy", "api_key": "dummy"},
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_filter_rejects_non_owned_file(self) -> None:
        self.register("alice", "pwd12345")
        self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")
        upload_payload = self.upload_bibliography(alice_headers)

        response = self.client.post(
            "/api/filter/start",
            headers=bob_headers,
            json={
                "file_id": upload_payload["file_id"],
                "mode": "explorer",
                "topic": "policy",
                "api_key": "dummy-key",
            },
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_filter_rejects_non_bibliography_file(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        upload_response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        self.assertEqual(upload_response.status_code, 200, upload_response.text)
        file_id = upload_response.json()["file_id"]

        response = self.client.post(
            "/api/filter/start",
            headers=headers,
            json={
                "file_id": file_id,
                "mode": "explorer",
                "topic": "policy",
                "api_key": "dummy-key",
            },
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_filter_creates_job_bib_links_and_artifact(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        upload_payload = self.upload_bibliography(headers)

        start_payload = self.start_filter(headers, upload_payload["file_id"])
        task_id = start_payload["task_id"]

        status_response = self.client.get(f"/api/filter/task/{task_id}/status", headers=headers)
        self.assertEqual(status_response.status_code, 200, status_response.text)
        status_payload = status_response.json()
        self.assertEqual(status_payload["status"], "completed")
        self.assertEqual(status_payload["result"]["row_count"], 2)

        with Session(self.sync_engine) as session:
            job = session.execute(select(Job).where(Job.id == task_id)).scalar_one()
            self.assertEqual(job.owner_user_id, 1)
            self.assertEqual(job.job_type, "filter")
            self.assertEqual(job.status, "success")
            self.assertEqual(job.input_file_id, upload_payload["file_id"])
            self.assertIsNotNone(job.expires_at)

            bib_entries = session.execute(select(BibEntry).where(BibEntry.owner_user_id == 1)).scalars().all()
            self.assertEqual(len(bib_entries), 1)
            self.assertEqual(bib_entries[0].source_db, "wos")
            self.assertEqual(bib_entries[0].source_filter_job_id, task_id)
            self.assertEqual(bib_entries[0].reading_status, "none")
            self.assertIsNotNone(bib_entries[0].expires_at)

            links = session.execute(select(BibFilterLink).where(BibFilterLink.filter_job_id == task_id)).scalars().all()
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0].passed, 1)
            self.assertIsNotNone(links[0].score)
            self.assertEqual(links[0].reason, "matched:policy")

            artifact = session.execute(
                select(Artifact).where(Artifact.job_id == task_id, Artifact.artifact_type == "filter_excel")
            ).scalar_one()
            self.assertEqual(artifact.owner_user_id, 1)
            artifact_path = TEST_RESULTS_ROOT / artifact.storage_path
            self.assertTrue(artifact_path.exists())
            self.assertIn(f"1/{task_id}/", artifact.storage_path.replace("\\", "/"))

    def test_filter_reuses_existing_bib_entry_for_same_user(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        upload_payload = self.upload_bibliography(headers)

        first = self.start_filter(headers, upload_payload["file_id"], topic="policy-a")
        second = self.start_filter(headers, upload_payload["file_id"], topic="policy-b")

        with Session(self.sync_engine) as session:
            bib_entries = session.execute(select(BibEntry).where(BibEntry.owner_user_id == 1)).scalars().all()
            self.assertEqual(len(bib_entries), 1)
            links = session.execute(select(BibFilterLink).order_by(BibFilterLink.filter_job_id)).scalars().all()
            self.assertEqual(len(links), 2)
            self.assertNotEqual(first["task_id"], second["task_id"])

    def test_filter_creates_separate_bib_entries_for_different_users(self) -> None:
        self.register("alice", "pwd12345")
        self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")

        alice_file = self.upload_bibliography(alice_headers)
        bob_file = self.upload_bibliography(bob_headers)

        self.start_filter(alice_headers, alice_file["file_id"], topic="alice")
        self.start_filter(bob_headers, bob_file["file_id"], topic="bob")

        with Session(self.sync_engine) as session:
            bib_entries = session.execute(select(BibEntry).order_by(BibEntry.owner_user_id)).scalars().all()
            self.assertEqual(len(bib_entries), 2)
            self.assertNotEqual(bib_entries[0].owner_user_id, bib_entries[1].owner_user_id)

    def test_filter_status_and_cancel_require_owner(self) -> None:
        self.register("alice", "pwd12345")
        self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")
        upload_payload = self.upload_bibliography(alice_headers)
        start_payload = self.start_filter(alice_headers, upload_payload["file_id"])
        task_id = start_payload["task_id"]

        status_response = self.client.get(f"/api/filter/task/{task_id}/status", headers=bob_headers)
        self.assertEqual(status_response.status_code, 404, status_response.text)

        cancel_response = self.client.post(f"/api/filter/task/{task_id}/cancel", headers=bob_headers)
        self.assertEqual(cancel_response.status_code, 404, cancel_response.text)

    def test_filter_empty_after_basic_filter_marks_job_failed(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        upload_payload = self.upload_bibliography(headers)

        start_payload = self.start_filter(headers, upload_payload["file_id"], min_year=2035)
        task_id = start_payload["task_id"]
        status_response = self.client.get(f"/api/filter/task/{task_id}/status", headers=headers)
        self.assertEqual(status_response.status_code, 200, status_response.text)
        self.assertEqual(status_response.json()["status"], "failed")

        with Session(self.sync_engine) as session:
            job = session.execute(select(Job).where(Job.id == task_id)).scalar_one()
            self.assertEqual(job.status, "failed")
            self.assertIn("过滤后无匹配文献", job.error_msg or "")
            self.assertEqual(session.query(BibEntry).count(), 0)
            self.assertEqual(session.query(BibFilterLink).count(), 0)
            self.assertEqual(session.query(Artifact).count(), 0)


if __name__ == "__main__":
    unittest.main()
