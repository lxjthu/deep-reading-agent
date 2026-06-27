from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-writing-style-analysis-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_writing_style_analysis.sqlite"
TEST_UPLOAD_ROOT = Path(TEMP_DIR) / "_uploads"
TEST_RESULTS_ROOT = Path(TEMP_DIR) / "results"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["UPLOAD_ROOT_DIR"] = TEST_UPLOAD_ROOT.as_posix()
os.environ["RESULTS_ROOT_DIR"] = TEST_RESULTS_ROOT.as_posix()
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

from db import Base  # noqa: E402
from db.models import Artifact, BibEntry, File, Job, User  # noqa: E402
from services.writing_style_analysis import (  # noqa: E402
    MissingMarkdownSourceError,
    analyze_library_writing_style,
)


class WritingStyleAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sync_engine = create_engine(f"sqlite:///{TEST_DB_PATH.as_posix()}")
        cls.async_engine = create_async_engine(f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}")
        cls.AsyncSessionLocal = async_sessionmaker(cls.async_engine, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.sync_engine.dispose()
        asyncio.run(cls.async_engine.dispose())
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    def seed_user(self) -> int:
        with Session(self.sync_engine) as session:
            user = User(username="style-user", password_hash="x", role="vip")
            session.add(user)
            session.commit()
            session.refresh(user)
            return int(user.id)

    def seed_entry(self, user_id: int, entry_id: str, *, markdown: str | None) -> None:
        file_id = None
        if markdown is not None:
            file_id = f"{entry_id}-md"
            md_path = TEST_UPLOAD_ROOT / f"{entry_id}.md"
            md_path.write_text(markdown, encoding="utf-8")
        with Session(self.sync_engine) as session:
            if file_id is not None:
                session.add(
                    File(
                        id=file_id,
                        owner_user_id=user_id,
                        original_name=f"{entry_id}.md",
                        file_type="markdown",
                        storage_path=md_path.as_posix(),
                        size_bytes=md_path.stat().st_size,
                        md5=f"{entry_id}-md5",
                    )
                )
            session.add(
                BibEntry(
                    id=entry_id,
                    owner_user_id=user_id,
                    title=f"Style Paper {entry_id}",
                    authors_json=json.dumps(["Alice"], ensure_ascii=False),
                    year=2026,
                    journal="管理世界",
                    keywords_json="[]",
                    source_db="manual",
                    source_file_id=file_id,
                    markdown_source_file_id=file_id,
                    user_tags_json="[]",
                    reading_status="read" if file_id else "none",
                    metadata_completeness="partial",
                    dedup_key=f"dedup-{entry_id}",
                )
            )
            session.commit()

    def test_missing_markdown_creates_no_artifact(self) -> None:
        user_id = self.seed_user()
        self.seed_entry(user_id, "entry-missing", markdown=None)

        async def run():
            async with self.AsyncSessionLocal() as session:
                with self.assertRaises(MissingMarkdownSourceError):
                    await analyze_library_writing_style(
                        session,
                        owner_user_id=user_id,
                        entry_ids=["entry-missing"],
                        api_key="sk-test",
                        llm_call=lambda _slot, _payload: "unused",
                    )
                jobs = (await session.execute(select(Job))).scalars().all()
                artifacts = (await session.execute(select(Artifact))).scalars().all()
                return jobs, artifacts

        jobs, artifacts = asyncio.run(run())
        self.assertEqual(jobs, [])
        self.assertEqual(artifacts, [])

    def test_markdown_backed_entry_creates_writing_style_artifact(self) -> None:
        user_id = self.seed_user()
        self.seed_entry(
            user_id,
            "entry-ok",
            markdown="# 引言\n本文先提出研究缺口。\n# 方法\n方法部分交代样本与识别策略。\n",
        )

        async def run():
            async with self.AsyncSessionLocal() as session:
                result = await analyze_library_writing_style(
                    session,
                    owner_user_id=user_id,
                    entry_ids=["entry-ok"],
                    api_key="sk-test",
                    llm_call=lambda slot, payload: f"{slot}: 基于原文证据的分析\n{payload[:40]}",
                )
                artifact = await session.get(Artifact, result["artifact_id"])
                job = await session.get(Job, result["job_id"])
                return result, artifact, job

        result, artifact, job = asyncio.run(run())
        self.assertEqual(result["analyzed_count"], 1)
        self.assertEqual(result["skipped"], [])
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact.artifact_type, "writing_style_md")
        self.assertTrue((TEST_RESULTS_ROOT / artifact.storage_path).exists())
        self.assertEqual(job.job_type, "writing_style")
        self.assertEqual(job.status, "success")

    def test_single_markdown_entry_sends_full_text_and_omits_evidence_overview(self) -> None:
        user_id = self.seed_user()
        markdown = "# 引言\n第一段。\n# 模型\n公式 $y=x+1$。\n# 结论\n最后一段。\n"
        self.seed_entry(user_id, "entry-full", markdown=markdown)
        calls: list[tuple[str, str]] = []

        async def run():
            async with self.AsyncSessionLocal() as session:
                result = await analyze_library_writing_style(
                    session,
                    owner_user_id=user_id,
                    entry_ids=["entry-full"],
                    api_key="sk-test",
                    llm_call=lambda slot, payload: calls.append((slot, payload)) or f"{slot}: ok",
                )
                artifact = await session.get(Artifact, result["artifact_id"])
                report = (TEST_RESULTS_ROOT / artifact.storage_path).read_text(encoding="utf-8")
                return report

        report = asyncio.run(run())
        section_payload = calls[0][1]
        self.assertIn("单篇论文写作风格分析助手", calls[0][0])
        self.assertIn('"source_mode": "full_markdown"', section_payload)
        self.assertIn('"full_markdown"', section_payload)
        self.assertIn("公式 $y=x+1$", section_payload)
        self.assertNotIn("## 原文证据概览", report)

    def test_multiple_markdown_entries_use_sampled_sections(self) -> None:
        user_id = self.seed_user()
        self.seed_entry(user_id, "entry-a", markdown="# 引言\nA 引言。\n# 方法\nA 方法。\n# 结论\nA 结论。\n")
        self.seed_entry(user_id, "entry-b", markdown="# 引言\nB 引言。\n# 方法\nB 方法。\n# 结果\nB 结果。\n")
        calls: list[tuple[str, str]] = []

        async def run():
            async with self.AsyncSessionLocal() as session:
                result = await analyze_library_writing_style(
                    session,
                    owner_user_id=user_id,
                    entry_ids=["entry-a", "entry-b"],
                    api_key="sk-test",
                    llm_call=lambda slot, payload: calls.append((slot, payload)) or f"{slot}: ok",
                )
                artifact = await session.get(Artifact, result["artifact_id"])
                return (TEST_RESULTS_ROOT / artifact.storage_path).read_text(encoding="utf-8")

        report = asyncio.run(run())
        self.assertIn("批量论文写作风格分析助手", calls[0][0])
        self.assertIn('"source_mode": "sampled_sections"', calls[0][1])
        self.assertIn('"sections"', calls[0][1])
        self.assertNotIn('"full_markdown"', calls[0][1])
        self.assertIn("## 原文证据概览", report)


if __name__ == "__main__":
    unittest.main()
