from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-reading-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_reading.sqlite"
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
from db.models import Artifact, BibEntry, File, Job, JobBibEntry, ReadingItem  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import reading as reading_router  # noqa: E402
from routers import upload as upload_router  # noqa: E402


PENDING_READING_RUNS: list[tuple[tuple, dict]] = []


def run_pending_reading_tasks():
    pending = list(PENDING_READING_RUNS)
    PENDING_READING_RUNS.clear()
    for target_name, args, kwargs in pending:
        getattr(ReadingRouterTests, target_name)(*args, **kwargs)


class ReadingRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reading_router.RESULTS_ROOT = TEST_RESULTS_ROOT
        reading_router.RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

        cls._original_run_long = reading_router.run_long_context_task
        cls._original_run_quant = reading_router.run_quant_task
        cls._original_run_qual = reading_router.run_qual_task

        cls._patchers = [
            patch.object(reading_router, "run_long_context_task", lambda *args, **kwargs: PENDING_READING_RUNS.append(("fake_long", args, kwargs))),
            patch.object(reading_router, "run_quant_task", lambda *args, **kwargs: PENDING_READING_RUNS.append(("fake_quant", args, kwargs))),
            patch.object(reading_router, "run_qual_task", lambda *args, **kwargs: PENDING_READING_RUNS.append(("fake_qual", args, kwargs))),
        ]
        for patcher in cls._patchers:
            patcher.start()

        test_app = FastAPI()
        test_app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        test_app.include_router(upload_router.router, prefix="/api/upload", tags=["Upload"])
        test_app.include_router(reading_router.router, prefix="/api/reading", tags=["Reading"])
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
        reading_router.tasks.clear()
        PENDING_READING_RUNS.clear()

    def register(self, username: str, password: str) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "email": f"{username}@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def login_headers(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post("/api/auth/login", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def upload_pdf(self, headers: dict[str, str], *, filename: str = "paper.pdf") -> dict:
        response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": (filename, b"%PDF-1.4 test pdf", "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def upload_bibliography(self, headers: dict[str, str], *, filename: str = "refs.txt") -> dict:
        response = self.client.post(
            "/api/upload/",
            headers=headers,
            files={"file": (filename, b"FN Clarivate Analytics Web of Science\nAU Smith", "text/plain")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def create_bib_entry(self, owner_user_id: int, *, title: str) -> str:
        with Session(self.sync_engine) as session:
            bib = BibEntry(
                id=f"bib-{owner_user_id}-{abs(hash(title)) % 1000000}",
                owner_user_id=owner_user_id,
                title=title,
                authors_json='["测试作者"]',
                year=2024,
                doi=None,
                journal="测试期刊",
                abstract="摘要",
                keywords_json='["关键词"]',
                venue_type=None,
                citation_count=None,
                source_db="cnki",
                source_filter_job_id=None,
                source_file_id=None,
                user_tags_json="[]",
                user_note=None,
                is_pinned=0,
                reading_status="none",
                metadata_completeness="partial",
                dedup_key=f"title:{title}",
            )
            session.add(bib)
            session.commit()
            return bib.id

    @staticmethod
    def fake_long(task_id: str, user_id: int, bib_entry_id: str, file_path: str, analysis_dims, custom_question, extraction_method, api_key=None):
        import asyncio

        asyncio.run(reading_router.sync_job_and_bib_start(task_id, bib_entry_id, stage="执行长文本分析...", progress=20))
        result_dir = reading_router.get_results_dir(user_id, task_id)
        report_path = result_dir / "long_report.md"
        report_path.write_text("# long report\n\nok", encoding="utf-8")
        results = {
            "研究问题": "这篇文章回答了核心研究问题。",
            "理论框架": "理论框架围绕双重嵌入展开。",
        }
        reading_router.tasks[task_id]["status"] = "completed"
        reading_router.tasks[task_id]["progress"] = 100
        reading_router.tasks[task_id]["stage"] = "完成"
        reading_router.tasks[task_id]["result"] = {
            "output_path": reading_router.build_result_storage_path(report_path),
            "preview": "ok",
            "dimensions": analysis_dims,
        }
        asyncio.run(
            reading_router.finalize_reading_success(
                task_id,
                bib_entry_id,
                user_id,
                [{"artifact_type": "reading_final", "absolute_path": report_path}],
                reading_items=reading_router.build_long_reading_items(results),
            )
        )

    @staticmethod
    def fake_quant(task_id: str, user_id: int, bib_entry_id: str, file_path: str, api_key=None):
        import asyncio

        asyncio.run(reading_router.sync_job_and_bib_start(task_id, bib_entry_id, stage="执行七步精读...", progress=20))
        result_dir = reading_router.get_results_dir(user_id, task_id)
        step_path = result_dir / "step_1.md"
        final_path = result_dir / "quant_report.md"
        step_path.write_text("# step 1", encoding="utf-8")
        final_path.write_text("# quant final", encoding="utf-8")
        results = {
            "第一步：核心贡献识别": (
                "### **1. 研究主题与核心结论**\n\n文章指出了核心发现。\n\n"
                "### **2. 问题意识**\n\n问题意识聚焦政策冲击。"
            )
        }
        reading_router.tasks[task_id]["status"] = "completed"
        reading_router.tasks[task_id]["progress"] = 100
        reading_router.tasks[task_id]["stage"] = "完成"
        reading_router.tasks[task_id]["result"] = {
            "output_path": reading_router.build_result_storage_path(final_path),
            "preview": "ok",
            "steps": ["第一步：核心贡献识别"],
        }
        asyncio.run(
            reading_router.finalize_reading_success(
                task_id,
                bib_entry_id,
                user_id,
                [
                    {"artifact_type": "reading_step", "absolute_path": step_path},
                    {"artifact_type": "reading_final", "absolute_path": final_path},
                ],
                reading_items=reading_router.build_step_reading_items(results, mode="quant"),
            )
        )

    @staticmethod
    def fake_qual(task_id: str, user_id: int, bib_entry_id: str, file_path: str, api_key=None):
        import asyncio

        asyncio.run(reading_router.sync_job_and_bib_start(task_id, bib_entry_id, stage="执行四步精读...", progress=20))
        result_dir = reading_router.get_results_dir(user_id, task_id)
        final_path = result_dir / "qual_report.md"
        final_path.write_text("# qual final", encoding="utf-8")
        results = {
            "第一步：背景与问题": (
                "## 1. 论文分类\n\n案例研究。\n\n"
                "## 2. 核心问题\n\n核心问题是生态价值实现。"
            )
        }
        reading_router.tasks[task_id]["status"] = "completed"
        reading_router.tasks[task_id]["progress"] = 100
        reading_router.tasks[task_id]["stage"] = "完成"
        reading_router.tasks[task_id]["result"] = {
            "output_path": reading_router.build_result_storage_path(final_path),
            "preview": "ok",
            "steps": ["第一步：背景与问题"],
        }
        asyncio.run(
            reading_router.finalize_reading_success(
                task_id,
                bib_entry_id,
                user_id,
                [{"artifact_type": "reading_final", "absolute_path": final_path}],
                reading_items=reading_router.build_step_reading_items(results, mode="qual"),
            )
        )

    def start_long(self, headers: dict[str, str], file_id: str) -> dict:
        response = self.client.post(
            "/api/reading/long/start",
            headers=headers,
            json={
                "file_id": file_id,
                "analysis_dims": ["研究问题", "理论框架"],
                "custom_question": None,
                "extraction_method": "full",
                "api_key": "dummy",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        run_pending_reading_tasks()
        return response.json()

    def start_quant(self, headers: dict[str, str], file_id: str) -> dict:
        response = self.client.post(
            "/api/reading/quant/start",
            headers=headers,
            json={"file_id": file_id, "api_key": "dummy"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        run_pending_reading_tasks()
        return response.json()

    def start_qual(self, headers: dict[str, str], file_id: str) -> dict:
        response = self.client.post(
            "/api/reading/qual/start",
            headers=headers,
            json={"file_id": file_id, "api_key": "dummy"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        run_pending_reading_tasks()
        return response.json()

    def test_reading_long_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/reading/long/start",
            json={"file_id": "x", "analysis_dims": ["研究问题"], "api_key": "dummy"},
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_reading_quant_requires_authentication(self) -> None:
        response = self.client.post("/api/reading/quant/start", json={"file_id": "x", "api_key": "dummy"})
        self.assertEqual(response.status_code, 401, response.text)

    def test_reading_qual_requires_authentication(self) -> None:
        response = self.client.post("/api/reading/qual/start", json={"file_id": "x", "api_key": "dummy"})
        self.assertEqual(response.status_code, 401, response.text)

    def test_reading_rejects_non_owned_file(self) -> None:
        self.register("alice", "pwd12345")
        self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")
        payload = self.upload_pdf(alice_headers)

        response = self.client.post(
            "/api/reading/long/start",
            headers=bob_headers,
            json={"file_id": payload["file_id"], "analysis_dims": ["研究问题"], "api_key": "dummy"},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_reading_rejects_unsupported_file_type(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_payload = self.upload_bibliography(headers)

        response = self.client.post(
            "/api/reading/long/start",
            headers=headers,
            json={"file_id": bib_payload["file_id"], "analysis_dims": ["研究问题"], "api_key": "dummy"},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_reading_long_creates_job_target_link_and_artifact(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        payload = self.upload_pdf(headers)

        started = self.start_long(headers, payload["file_id"])
        task_id = started["task_id"]

        with Session(self.sync_engine) as session:
            job = session.execute(select(Job).where(Job.id == task_id)).scalar_one()
            self.assertEqual(job.job_type, "reading_long")
            self.assertEqual(job.owner_user_id, 1)
            self.assertEqual(job.status, "success")
            self.assertIsNotNone(job.expires_at)

            bib = session.execute(select(BibEntry).where(BibEntry.source_file_id == payload["file_id"])).scalar_one()
            self.assertEqual(bib.reading_status, "read")

            link = session.execute(select(JobBibEntry).where(JobBibEntry.job_id == task_id)).scalar_one()
            self.assertEqual(link.role, "target")
            self.assertEqual(link.bib_entry_id, bib.id)

            artifact = session.execute(select(Artifact).where(Artifact.job_id == task_id)).scalar_one()
            self.assertEqual(artifact.artifact_type, "reading_final")
            self.assertIn(f"1/{task_id}/", artifact.storage_path.replace("\\", "/"))
            self.assertTrue((TEST_RESULTS_ROOT / artifact.storage_path).exists())

    def test_reading_reuses_existing_bib_entry_for_source_file(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        payload = self.upload_pdf(headers)

        first = self.start_long(headers, payload["file_id"])
        second = self.start_qual(headers, payload["file_id"])

        with Session(self.sync_engine) as session:
            bib_entries = session.execute(select(BibEntry).where(BibEntry.owner_user_id == 1)).scalars().all()
            self.assertEqual(len(bib_entries), 1)
            links = session.execute(select(JobBibEntry).order_by(JobBibEntry.job_id)).scalars().all()
            self.assertEqual(len(links), 2)
            self.assertNotEqual(first["task_id"], second["task_id"])

    def test_reading_matches_existing_bib_by_similar_title(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_id = self.create_bib_entry(
            1,
            title="生态产品价值实现的中国经验-基于国家部委典型案例的实践解构与理论阐释",
        )
        payload = self.upload_pdf(
            headers,
            filename="生态产品价值实现的中国经验——基于国家部委典型案例的实践解构与理论阐释.pdf",
        )

        started = self.start_long(headers, payload["file_id"])

        with Session(self.sync_engine) as session:
            bib = session.execute(select(BibEntry).where(BibEntry.id == bib_id)).scalar_one()
            link = session.execute(select(JobBibEntry).where(JobBibEntry.job_id == started["task_id"])).scalar_one()
            self.assertEqual(bib.source_file_id, payload["file_id"])
            self.assertEqual(link.bib_entry_id, bib_id)

    def test_quant_writes_step_and_final_artifacts(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        payload = self.upload_pdf(headers)
        started = self.start_quant(headers, payload["file_id"])

        with Session(self.sync_engine) as session:
            artifacts = session.execute(
                select(Artifact).where(Artifact.job_id == started["task_id"]).order_by(Artifact.sort_order)
            ).scalars().all()
            self.assertEqual(len(artifacts), 2)
            self.assertEqual(artifacts[0].artifact_type, "reading_step")
            self.assertEqual(artifacts[1].artifact_type, "reading_final")

    def test_long_writes_structured_reading_items(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        payload = self.upload_pdf(headers)
        started = self.start_long(headers, payload["file_id"])

        with Session(self.sync_engine) as session:
            items = session.execute(
                select(ReadingItem)
                .where(ReadingItem.job_id == started["task_id"])
                .order_by(ReadingItem.sort_order, ReadingItem.id)
            ).scalars().all()
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].mode, "long")
            self.assertEqual(items[0].section_type, "dimension")
            self.assertEqual(items[0].item_key, "long.research_question")
            self.assertEqual(items[1].item_key, "long.theory_framework")

    def test_quant_writes_step_and_subquestion_reading_items(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        payload = self.upload_pdf(headers)
        started = self.start_quant(headers, payload["file_id"])

        with Session(self.sync_engine) as session:
            items = session.execute(
                select(ReadingItem)
                .where(ReadingItem.job_id == started["task_id"])
                .order_by(ReadingItem.sort_order, ReadingItem.id)
            ).scalars().all()
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0].section_type, "step")
            self.assertEqual(items[0].item_key, "quant.step1")
            self.assertEqual(items[1].section_type, "subquestion")
            self.assertEqual(items[1].item_label, "1. 研究主题与核心结论")
            self.assertEqual(items[2].item_key, "quant.step1.q2")

    def test_qual_writes_step_and_subquestion_reading_items(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        payload = self.upload_pdf(headers)
        started = self.start_qual(headers, payload["file_id"])

        with Session(self.sync_engine) as session:
            items = session.execute(
                select(ReadingItem)
                .where(ReadingItem.job_id == started["task_id"])
                .order_by(ReadingItem.sort_order, ReadingItem.id)
            ).scalars().all()
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0].item_key, "qual.step1")
            self.assertEqual(items[1].item_key, "qual.step1.q1")
            self.assertEqual(items[2].item_label, "2. 核心问题")

    def test_reading_status_and_cancel_require_owner(self) -> None:
        self.register("alice", "pwd12345")
        self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")
        payload = self.upload_pdf(alice_headers)
        started = self.start_long(alice_headers, payload["file_id"])
        task_id = started["task_id"]

        status_response = self.client.get(f"/api/reading/task/{task_id}/status", headers=bob_headers)
        self.assertEqual(status_response.status_code, 404, status_response.text)

        cancel_response = self.client.post(f"/api/reading/task/{task_id}/cancel", headers=bob_headers)
        self.assertEqual(cancel_response.status_code, 404, cancel_response.text)

    def test_reading_status_endpoint_replays_db_result(self) -> None:
        self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        payload = self.upload_pdf(headers)
        started = self.start_long(headers, payload["file_id"])
        task_id = started["task_id"]
        reading_router.tasks.pop(task_id, None)

        status_response = self.client.get(f"/api/reading/task/{task_id}/status", headers=headers)
        self.assertEqual(status_response.status_code, 200, status_response.text)
        body = status_response.json()
        self.assertEqual(body["status"], "completed")
        self.assertIn("output_path", body["result"])


if __name__ == "__main__":
    unittest.main()
