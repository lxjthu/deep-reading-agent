from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-backfill-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_backfill.sqlite"
TEST_RESULTS_ROOT = Path(TEMP_DIR) / "results"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["RESULTS_ROOT_DIR"] = TEST_RESULTS_ROOT.as_posix()

from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import Artifact, BibEntry, Job, JobBibEntry, ReadingItem, User  # noqa: E402
from scripts.backfill_reading_items import backfill_reading_items  # noqa: E402


class BackfillReadingItemsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    def seed_reading_job(
        self,
        *,
        job_type: str,
        report_filename: str,
        report_content: str,
        params_json: str = "{}",
        with_existing_items: bool = False,
    ) -> str:
        job_id = f"job-{job_type}-{abs(hash(report_filename)) % 100000}"
        bib_id = f"bib-{abs(hash((job_type, report_filename))) % 100000}"
        user_id = 1
        report_rel = Path(str(user_id)) / job_id / report_filename
        report_path = TEST_RESULTS_ROOT / report_rel
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_content, encoding="utf-8")

        with Session(self.sync_engine) as session:
            session.add(
                User(
                    id=user_id,
                    username="alice",
                    email="alice@example.com",
                    password_hash="hash",
                    role="vip",
                    is_active=1,
                    token_version=0,
                )
            )
            session.add(
                BibEntry(
                    id=bib_id,
                    owner_user_id=user_id,
                    title="测试文献",
                    authors_json='["Alice"]',
                    year=2024,
                    doi=None,
                    journal="Journal",
                    abstract="摘要",
                    keywords_json="[]",
                    venue_type=None,
                    citation_count=None,
                    source_db="pdf_extracted",
                    source_filter_job_id=None,
                    source_file_id=None,
                    user_tags_json="[]",
                    user_note=None,
                    is_pinned=0,
                    reading_status="read",
                    metadata_completeness="full",
                    dedup_key=f"dedup:{bib_id}",
                    expires_at=None,
                )
            )
            session.add(
                Job(
                    id=job_id,
                    owner_user_id=user_id,
                    job_type=job_type,
                    status="success",
                    input_file_id=None,
                    params_json=params_json,
                    progress=100,
                    current_stage="完成",
                    expires_at=None,
                )
            )
            session.add(
                JobBibEntry(
                    job_id=job_id,
                    bib_entry_id=bib_id,
                    role="target",
                    sort_order=0,
                )
            )
            session.add(
                Artifact(
                    job_id=job_id,
                    owner_user_id=user_id,
                    artifact_type="reading_final",
                    filename=report_filename,
                    storage_path=report_rel.as_posix(),
                    size_bytes=report_path.stat().st_size,
                    expires_at=None,
                )
            )
            if with_existing_items:
                session.add(
                    ReadingItem(
                        owner_user_id=user_id,
                        bib_entry_id=bib_id,
                        job_id=job_id,
                        mode="long",
                        section_type="dimension",
                        parent_key=None,
                        item_key="long.research_question",
                        item_label="研究问题",
                        sort_order=0,
                        content="已有内容",
                    )
                )
            session.commit()

        return job_id

    def test_backfill_long_report_persists_dimension_items(self) -> None:
        job_id = self.seed_reading_job(
            job_type="reading_long",
            report_filename="paper_long_context.md",
            report_content=(
                "---\n"
                "title: 测试\n"
                "---\n"
                "# 长文本精读报告\n\n"
                "## 分析维度\n\n"
                "<!--DIMENSIONS_START-->\n\n"
                "### 研究问题\n\n这里是研究问题分析。\n\n"
                "<!--DIMENSION_BOUNDARY-->\n\n"
                "### 理论框架\n\n这里是理论框架分析。\n\n"
                "<!--DIMENSION_BOUNDARY-->\n\n"
                "<!--DIMENSIONS_END-->\n"
            ),
            params_json='{"custom_question":"政策启示是什么？"}',
        )

        stats = asyncio.run(backfill_reading_items())
        self.assertEqual(stats.created_items, 2)

        with Session(self.sync_engine) as session:
            items = session.execute(
                select(ReadingItem).where(ReadingItem.job_id == job_id).order_by(ReadingItem.sort_order)
            ).scalars().all()
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0].item_key, "long.research_question")
            self.assertEqual(items[1].item_key, "long.theory_framework")

    def test_backfill_quant_report_persists_subquestion_items(self) -> None:
        job_id = self.seed_reading_job(
            job_type="reading_quant",
            report_filename="paper_7step.md",
            report_content=(
                "# 七步精读报告\n\n"
                "## 第一步：核心贡献识别\n\n"
                "### **1. 研究主题与核心结论**\n\n文章指出核心发现。\n\n"
                "### **2. 问题意识**\n\n文章聚焦政策冲击。\n\n"
                "---\n\n"
            ),
        )

        stats = asyncio.run(backfill_reading_items())
        self.assertEqual(stats.created_items, 3)

        with Session(self.sync_engine) as session:
            items = session.execute(
                select(ReadingItem).where(ReadingItem.job_id == job_id).order_by(ReadingItem.sort_order)
            ).scalars().all()
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0].item_key, "quant.step1")
            self.assertEqual(items[1].item_key, "quant.step1.q1")
            self.assertEqual(items[2].item_label, "2. 问题意识")

    def test_backfill_is_idempotent_and_dry_run_safe(self) -> None:
        self.seed_reading_job(
            job_type="reading_qual",
            report_filename="paper_4step.md",
            report_content=(
                "# 四步精读报告\n\n"
                "## 第一步：背景与问题\n\n"
                "## 1. 论文分类\n\n案例研究。\n\n"
                "## 2. 核心问题\n\n生态价值实现。\n\n"
            ),
            with_existing_items=True,
        )

        dry_stats = asyncio.run(backfill_reading_items(dry_run=True))
        self.assertEqual(dry_stats.skipped_existing, 1)

        with Session(self.sync_engine) as session:
            count = session.execute(select(ReadingItem)).scalars().all()
            self.assertEqual(len(count), 1)


if __name__ == "__main__":
    unittest.main()
