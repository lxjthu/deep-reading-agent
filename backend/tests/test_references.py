from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-reference-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_references.sqlite"
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
from db.models import BibEntry, File, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import references as references_router  # noqa: E402


PENDING_REFERENCE_RUNS: list[tuple[tuple, dict]] = []


def run_pending_reference_tasks():
    pending = list(PENDING_REFERENCE_RUNS)
    PENDING_REFERENCE_RUNS.clear()
    for target_name, args, kwargs in pending:
        getattr(ReferenceRouterTests, target_name)(*args, **kwargs)


class ReferenceRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        references_router.RESULTS_ROOT = TEST_RESULTS_ROOT
        references_router.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

        cls._patcher = patch.object(
            references_router,
            "run_reference_trace_task",
            lambda *args, **kwargs: PENDING_REFERENCE_RUNS.append(("fake_reference_trace", args, kwargs)),
        )
        cls._patcher.start()

        test_app = FastAPI()
        test_app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        test_app.include_router(references_router.router, prefix="/api/references", tags=["References"])
        cls.client = TestClient(test_app)
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())
        cls._patcher.stop()
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        references_router.tasks.clear()
        PENDING_REFERENCE_RUNS.clear()

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

    def create_pdf_entry(self, owner_user_id: int, *, title: str = "Source Paper") -> tuple[str, str]:
        file_id = str(uuid.uuid4())
        bib_id = str(uuid.uuid4())
        upload_dir = TEST_UPLOAD_ROOT / str(owner_user_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / f"{file_id}.pdf"
        file_path.write_bytes(b"%PDF-1.4 fake pdf")

        with Session(self.sync_engine) as session:
            session.add(
                File(
                    id=file_id,
                    owner_user_id=owner_user_id,
                    original_name=f"{title}.pdf",
                    file_type="pdf",
                    storage_path=file_path.as_posix(),
                    size_bytes=file_path.stat().st_size,
                    md5=f"md5-{file_id}",
                )
            )
            session.add(
                BibEntry(
                    id=bib_id,
                    owner_user_id=owner_user_id,
                    title=title,
                    authors_json='["Alice", "Bob"]',
                    year=2024,
                    doi=None,
                    journal="Journal",
                    abstract="Abstract",
                    keywords_json='["kw"]',
                    venue_type=None,
                    citation_count=None,
                    source_db="pdf_extracted",
                    source_filter_job_id=None,
                    source_file_id=file_id,
                    user_tags_json="[]",
                    user_note=None,
                    is_pinned=0,
                    reading_status="read",
                    metadata_completeness="partial",
                    dedup_key=f"sig:alice:2024:{title.lower()}",
                )
            )
            session.commit()
        return bib_id, file_id

    @staticmethod
    def fake_reference_trace(task_id: str, user_id: int, source_bib_entry_id: str, file_path: str, source_title: str) -> None:
        import asyncio

        asyncio.run(references_router.mark_trace_started(task_id, source_bib_entry_id, stage="测试梳理中", progress=20))
        references = [
            {
                "reference_order": 1,
                "raw_text": "[1] Smith, J. (2020). Platform Competition. Journal of Tests, 10(2), 1-20.",
                "authors": ["Smith, J."],
                "year": 2020,
                "title": "Platform Competition",
                "journal": "Journal of Tests",
                "volume": "10",
                "issue": "2",
                "pages": "1-20",
                "doi": "10.1000/platform",
                "language": "en",
                "dedup_key": "doi:10.1000/platform",
                "citations": [
                    {
                        "page_label": "第1页",
                        "paragraph_label": "P1-1",
                        "quote_text": "(Smith, 2020)",
                        "excerpt": "The mechanism follows prior work (Smith, 2020) and extends the platform model.",
                        "char_start": 10,
                        "char_end": 23,
                        "match_method": "author_year",
                        "confidence": 0.92,
                    }
                ],
            },
            {
                "reference_order": 2,
                "raw_text": "[2] 张三，李四. 生态治理与乡村发展[J]. 中国农村研究, 2021(3): 12-20.",
                "authors": ["张三", "李四"],
                "year": 2021,
                "title": "生态治理与乡村发展",
                "journal": "中国农村研究",
                "volume": None,
                "issue": "3",
                "pages": "12-20",
                "doi": None,
                "language": "zh",
                "dedup_key": "sig:张三:2021:生态治理与乡村发展",
                "citations": [],
            },
        ]
        artifact_files = references_router.write_trace_outputs(user_id, task_id, source_title, references)
        asyncio.run(
            references_router.persist_trace_success(
                task_id,
                user_id,
                source_bib_entry_id,
                references,
                artifact_files,
            )
        )
        references_router.tasks[task_id]["status"] = "completed"
        references_router.tasks[task_id]["progress"] = 100
        references_router.tasks[task_id]["stage"] = "完成"
        references_router.tasks[task_id]["logs"] = ["测试梳理完成"]
        references_router.tasks[task_id]["result"] = {"artifacts": artifact_files}

    def test_reference_trace_endpoints_flow(self) -> None:
        owner_id = self.register("alice")
        bib_id, _file_id = self.create_pdf_entry(owner_id, title="Reference Source")
        headers = self.login_headers("alice")

        entries_res = self.client.get("/api/references/entries", headers=headers)
        self.assertEqual(entries_res.status_code, 200, entries_res.text)
        self.assertEqual(len(entries_res.json()), 1)

        start_res = self.client.post(
            f"/api/references/entries/{bib_id}/trace",
            headers=headers,
            json={},
        )
        self.assertEqual(start_res.status_code, 200, start_res.text)
        task_id = start_res.json()["task_id"]

        run_pending_reference_tasks()

        status_res = self.client.get(f"/api/references/task/{task_id}/status", headers=headers)
        self.assertEqual(status_res.status_code, 200, status_res.text)
        self.assertEqual(status_res.json()["status"], "completed")

        summary_res = self.client.get(f"/api/references/entries/{bib_id}/summary", headers=headers)
        self.assertEqual(summary_res.status_code, 200, summary_res.text)
        summary = summary_res.json()
        self.assertEqual(summary["reference_count"], 2)
        self.assertEqual(summary["citation_hit_count"], 1)
        self.assertEqual(len(summary["latest_task"]["artifacts"]), 4)

        refs_res = self.client.get(f"/api/references/entries/{bib_id}/references", headers=headers)
        self.assertEqual(refs_res.status_code, 200, refs_res.text)
        refs = refs_res.json()
        self.assertEqual(len(refs), 2)
        first_ref_id = refs[0]["id"]
        second_ref_id = refs[1]["id"]
        self.assertEqual(refs[0]["citation_count"], 1)

        citations_res = self.client.get(
            f"/api/references/references/{first_ref_id}/citations",
            headers=headers,
        )
        self.assertEqual(citations_res.status_code, 200, citations_res.text)
        self.assertEqual(len(citations_res.json()), 1)

        import_res = self.client.post(
            f"/api/references/references/{second_ref_id}/import",
            headers=headers,
        )
        self.assertEqual(import_res.status_code, 200, import_res.text)
        self.assertEqual(import_res.json()["source"], "created")

        refs_after_import = self.client.get(f"/api/references/entries/{bib_id}/references", headers=headers)
        self.assertEqual(refs_after_import.status_code, 200, refs_after_import.text)
        imported = [item for item in refs_after_import.json() if item["id"] == second_ref_id][0]
        self.assertEqual(imported["match_method"], "imported")


if __name__ == "__main__":
    unittest.main()
