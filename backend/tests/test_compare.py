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

TEMP_DIR = tempfile.mkdtemp(prefix="dra-compare-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_compare.sqlite"
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
from db.models import Artifact, BibEntry, Job, JobBibEntry, ReadingItem, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import compare as compare_router  # noqa: E402
from routers import history as history_router  # noqa: E402


class _FakeChoice:
    def __init__(self, content: str):
        self.message = types.SimpleNamespace(content=content)


class _FakeChatCompletions:
    def create(self, **kwargs):
        return types.SimpleNamespace(choices=[_FakeChoice("比较综述正文。")])


class _FakeOpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = types.SimpleNamespace(completions=_FakeChatCompletions())


class CompareRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compare_router.RESULTS_ROOT = TEST_RESULTS_ROOT
        history_router.RESULTS_DIR = TEST_RESULTS_ROOT.as_posix()
        history_router.FILTER_DIR = (TEST_RESULTS_ROOT / "literature_filter").as_posix()
        history_router.SYNTHESIS_DIR = (TEST_RESULTS_ROOT / "synthesis").as_posix()
        Path(history_router.SYNTHESIS_DIR).mkdir(parents=True, exist_ok=True)

        cls._patchers = [
            patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=_FakeOpenAI)}),
        ]
        for patcher in cls._patchers:
            patcher.start()

        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        app.include_router(compare_router.router, prefix="/api/compare", tags=["Compare"])
        app.include_router(history_router.router, prefix="/api/history", tags=["History"])
        cls.client = TestClient(app)
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
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        Path(history_router.SYNTHESIS_DIR).mkdir(parents=True, exist_ok=True)

    def register(self, username: str, password: str) -> int:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "email": f"{username}@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.sync_engine) as session:
            user = session.execute(select(User).where(User.username == username)).scalar_one()
            return user.id

    def login_headers(self, username: str, password: str) -> dict[str, str]:
        response = self.client.post("/api/auth/login", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_bib_entry(self, owner_user_id: int, title: str, *, doi: str | None = None) -> str:
        with Session(self.sync_engine) as session:
            bib = BibEntry(
                id=f"bib-{owner_user_id}-{abs(hash((owner_user_id, title, doi))) % 1000000}",
                owner_user_id=owner_user_id,
                title=title,
                authors_json='["Alice Smith"]',
                year=2024,
                doi=doi,
                journal="Journal of Testing",
                abstract="Abstract",
                keywords_json='["test"]',
                venue_type="journal",
                citation_count=1,
                source_db="wos",
                source_filter_job_id=None,
                source_file_id=None,
                user_tags_json="[]",
                user_note=None,
                is_pinned=0,
                reading_status="read",
                metadata_completeness="full",
                dedup_key=f"doi:{doi}" if doi else f"title:{title.lower()}",
                expires_at=None,
            )
            session.add(bib)
            session.commit()
            return bib.id

    def seed_reading_item(
        self,
        owner_user_id: int,
        bib_entry_id: str,
        *,
        mode: str,
        section_type: str,
        item_key: str,
        item_label: str,
        content: str,
        parent_key: str | None = None,
        sort_order: int = 0,
        job_id: str | None = None,
    ) -> None:
        with Session(self.sync_engine) as session:
            session.add(
                ReadingItem(
                    owner_user_id=owner_user_id,
                    bib_entry_id=bib_entry_id,
                    job_id=job_id or f"job-{bib_entry_id}-{item_key}",
                    mode=mode,
                    section_type=section_type,
                    parent_key=parent_key,
                    item_key=item_key,
                    item_label=item_label,
                    sort_order=sort_order,
                    content=content,
                )
            )
            session.commit()

    def compare_payload(self, bib_entry_ids: list[str]) -> dict:
        return {
            "step": "第一步：研究问题",
            "papers": ["A", "B"],
            "subQuestions": ["研究问题"],
            "paperData": [
                {
                    "title": "Paper A",
                    "authors": ["Alice Smith"],
                    "year": 2024,
                    "journal": "Journal A",
                    "doi": "10.1000/a",
                    "subQuestions": {"研究问题": "paper a content"},
                },
                {
                    "title": "Paper B",
                    "authors": ["Bob Jones"],
                    "year": 2023,
                    "journal": "Journal B",
                    "doi": "10.1000/b",
                    "subQuestions": {"研究问题": "paper b content"},
                },
            ],
            "bib_entry_ids": bib_entry_ids,
            "api_key": "dummy-key",
            "mode": "single",
        }

    def test_compare_requires_authentication(self) -> None:
        response = self.client.post("/api/compare/analyze", json=self.compare_payload(["a", "b"]))
        self.assertEqual(response.status_code, 401, response.text)

    def test_compare_rejects_non_owned_bib_entry(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        bob_id = self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        alice_bib = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")
        bob_bib = self.create_bib_entry(bob_id, "Paper B", doi="10.1000/b")

        payload = self.compare_payload([alice_bib, bob_bib])
        response = self.client.post("/api/compare/analyze", headers=alice_headers, json=payload)
        self.assertEqual(response.status_code, 404, response.text)

    def test_compare_requires_at_least_two_members(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        alice_bib = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")

        payload = self.compare_payload([alice_bib])
        response = self.client.post("/api/compare/analyze", headers=headers, json=payload)
        self.assertEqual(response.status_code, 400, response.text)

    def test_compare_creates_job_and_compare_members(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_a = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")
        bib_b = self.create_bib_entry(alice_id, "Paper B", doi="10.1000/b")

        response = self.client.post("/api/compare/analyze", headers=headers, json=self.compare_payload([bib_a, bib_b]))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("synthesis", body)
        self.assertIn("job_id", body)

        with Session(self.sync_engine) as session:
            job = session.execute(select(Job).where(Job.id == body["job_id"])).scalar_one()
            self.assertEqual(job.owner_user_id, alice_id)
            self.assertEqual(job.job_type, "compare")
            self.assertEqual(job.status, "success")

            links = session.execute(
                select(JobBibEntry).where(JobBibEntry.job_id == body["job_id"]).order_by(JobBibEntry.sort_order)
            ).scalars().all()
            self.assertEqual(len(links), 2)
            self.assertEqual({link.role for link in links}, {"compare_member"})

            artifact = session.execute(
                select(Artifact).where(Artifact.job_id == body["job_id"], Artifact.artifact_type == "compare_md")
            ).scalar_one()
            self.assertTrue((TEST_RESULTS_ROOT / artifact.storage_path).exists())
            self.assertIn(f"{alice_id}/{body['job_id']}/", artifact.storage_path.replace("\\", "/"))

    def test_compare_keeps_response_text_for_frontend(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_a = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")
        bib_b = self.create_bib_entry(alice_id, "Paper B", doi="10.1000/b")

        response = self.client.post("/api/compare/analyze_long", headers=headers, json={
            "dimension": "理论框架",
            "papers": ["A", "B"],
            "paperData": [
                {"title": "Paper A", "authors": ["Alice Smith"], "year": 2024, "journal": "Journal A", "doi": "10.1000/a", "content": "aaa"},
                {"title": "Paper B", "authors": ["Bob Jones"], "year": 2023, "journal": "Journal B", "doi": "10.1000/b", "content": "bbb"},
            ],
            "bib_entry_ids": [bib_a, bib_b],
            "api_key": "dummy-key",
            "mode": "single",
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("比较综述正文", response.json()["synthesis"])

    def test_compare_can_build_prompt_from_structured_reading_items(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_a = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")
        bib_b = self.create_bib_entry(alice_id, "Paper B", doi="10.1000/b")
        self.seed_reading_item(
            alice_id,
            bib_a,
            mode="quant",
            section_type="subquestion",
            item_key="quant.step1.q1",
            item_label="研究问题",
            content="A 文献认为生态治理依赖制度协同。",
        )
        self.seed_reading_item(
            alice_id,
            bib_b,
            mode="quant",
            section_type="subquestion",
            item_key="quant.step1.q1",
            item_label="研究问题",
            content="B 文献强调地方试点与激励设计。",
        )

        payload = self.compare_payload([bib_a, bib_b])
        payload["paperData"] = []
        response = self.client.post("/api/compare/analyze", headers=headers, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("比较综述正文", response.json()["synthesis"])

    def test_structured_reading_endpoint_groups_qual_step_subquestions(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_id = self.create_bib_entry(alice_id, "生态产品价值实现的中国经验")
        job_id = "job-qual-1"

        with Session(self.sync_engine) as session:
            session.add(Job(id=job_id, owner_user_id=alice_id, job_type="reading_qual", status="success"))
            session.add(JobBibEntry(job_id=job_id, bib_entry_id=bib_id, role="target", sort_order=0))
            session.commit()

        self.seed_reading_item(
            alice_id,
            bib_id,
            job_id=job_id,
            mode="qual",
            section_type="step",
            item_key="qual.step1",
            item_label="第一步：背景与问题",
            content="",
            sort_order=0,
        )
        self.seed_reading_item(
            alice_id,
            bib_id,
            job_id=job_id,
            mode="qual",
            section_type="subquestion",
            parent_key="qual.step1",
            item_key="qual.step1.q1",
            item_label="1. 论文分类",
            content="案例研究。",
            sort_order=1,
        )
        self.seed_reading_item(
            alice_id,
            bib_id,
            job_id=job_id,
            mode="qual",
            section_type="subquestion",
            parent_key="qual.step1",
            item_key="qual.step1.q2",
            item_label="2. 核心问题",
            content="生态产品价值实现。",
            sort_order=2,
        )

        response = self.client.get(f"/api/compare/jobs/{job_id}/structured", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["mode"], "qual")
        self.assertEqual(body["title"], "生态产品价值实现的中国经验")
        self.assertIn("第一步", body["steps"])
        self.assertEqual(body["steps"]["第一步"]["label"], "第一步：背景与问题")
        self.assertEqual(body["steps"]["第一步"]["sub_questions"]["1. 论文分类"], "案例研究。")

    def test_save_synthesis_requires_authentication(self) -> None:
        response = self.client.post(
            "/api/history/synthesis/",
            json={"dimension": "研究问题", "papers": ["A"], "content": "hello", "bib_entry_ids": ["x"]},
        )
        self.assertEqual(response.status_code, 401, response.text)

    def test_save_synthesis_creates_job_members_and_artifact(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_a = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")
        bib_b = self.create_bib_entry(alice_id, "Paper B", doi="10.1000/b")

        response = self.client.post(
            "/api/history/synthesis/",
            headers=headers,
            json={
                "dimension": "研究问题",
                "papers": ["Paper A", "Paper B"],
                "content": "综合综述内容",
                "bib_entry_ids": [bib_a, bib_b],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        with Session(self.sync_engine) as session:
            job = session.execute(select(Job).where(Job.id == body["job_id"])).scalar_one()
            self.assertEqual(job.job_type, "synthesis")
            self.assertEqual(job.status, "success")

            links = session.execute(
                select(JobBibEntry).where(JobBibEntry.job_id == body["job_id"]).order_by(JobBibEntry.sort_order)
            ).scalars().all()
            self.assertEqual(len(links), 2)
            self.assertEqual({link.role for link in links}, {"synthesis_member"})

            artifact = session.execute(
                select(Artifact).where(Artifact.job_id == body["job_id"], Artifact.artifact_type == "synthesis_md")
            ).scalar_one()
            self.assertTrue((TEST_RESULTS_ROOT / artifact.storage_path).exists())
            self.assertIn(f"{alice_id}/{body['job_id']}/", artifact.storage_path.replace("\\", "/"))

    def test_list_synthesis_only_returns_current_user_records(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        bob_id = self.register("bob", "pwd12345")
        alice_headers = self.login_headers("alice", "pwd12345")
        bob_headers = self.login_headers("bob", "pwd12345")
        alice_bib = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")
        bob_bib = self.create_bib_entry(bob_id, "Paper B", doi="10.1000/b")

        self.client.post(
            "/api/history/synthesis/",
            headers=alice_headers,
            json={"dimension": "研究问题", "papers": ["Paper A"], "content": "alice", "bib_entry_ids": [alice_bib]},
        )
        self.client.post(
            "/api/history/synthesis/",
            headers=bob_headers,
            json={"dimension": "研究问题", "papers": ["Paper B"], "content": "bob", "bib_entry_ids": [bob_bib]},
        )

        response = self.client.get("/api/history/synthesis/", headers=alice_headers)
        self.assertEqual(response.status_code, 200, response.text)
        files = response.json()["all"]
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0]["filename"].startswith("synthesis_"))

    def test_synthesis_paths_use_uid_jobid_layout(self) -> None:
        alice_id = self.register("alice", "pwd12345")
        headers = self.login_headers("alice", "pwd12345")
        bib_a = self.create_bib_entry(alice_id, "Paper A", doi="10.1000/a")

        response = self.client.post(
            "/api/history/synthesis/",
            headers=headers,
            json={"dimension": "理论框架", "papers": ["Paper A"], "content": "hello", "bib_entry_ids": [bib_a]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn(f"{alice_id}/{body['job_id']}/", body["path"].replace("\\", "/"))


if __name__ == "__main__":
    unittest.main()
