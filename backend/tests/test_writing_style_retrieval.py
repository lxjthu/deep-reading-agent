from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-writing-style-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_writing_style.sqlite"
UPLOAD_DIR = Path(TEMP_DIR) / "uploads"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["UPLOAD_ROOT_DIR"] = UPLOAD_DIR.as_posix()
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

from db import Base  # noqa: E402
from db.models import BibEntry, File, User  # noqa: E402
from services.writing_style_retrieval import (  # noqa: E402
    analyze_writing_style,
    detect_style_focus,
    extract_style_sections,
)


class WritingStyleRetrievalTests(unittest.TestCase):
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
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def seed_library(self) -> dict[str, str | int]:
        owner_id = 1
        other_owner_id = 2
        md_path = UPLOAD_DIR / "style-source.md"
        md_path.write_text(
            "\n".join(
                [
                    "---",
                    "title: sample",
                    "---",
                    "# 引言",
                    "第一段先提出数字治理的现实张力，并用一个清楚的研究缺口收束。",
                    "第二段把平台责任放进制度情境，说明本文为什么值得研究。",
                    "# 理论分析",
                    "理论部分从合法性压力推导平台责任，并连接组织响应机制。",
                    "# 研究方法",
                    "方法部分交代样本、变量和识别策略，不夸大因果。",
                ]
            ),
            encoding="utf-8",
        )

        from sqlalchemy.orm import Session

        with Session(self.sync_engine) as session:
            session.add_all(
                [
                    User(id=owner_id, username="owner", password_hash="x", role="vip"),
                    User(id=other_owner_id, username="other", password_hash="x", role="vip"),
                    File(
                        id="file-style",
                        owner_user_id=owner_id,
                        original_name="style-source.md",
                        file_type="markdown",
                        storage_path=md_path.as_posix(),
                        size_bytes=md_path.stat().st_size,
                        md5="style-md5",
                    ),
                    BibEntry(
                        id="entry-style",
                        owner_user_id=owner_id,
                        title="Platform Responsibility Writing",
                        authors_json=json.dumps(["宁健康", "Alice"]),
                        year=2024,
                        journal="管理世界",
                        abstract="A style sample.",
                        keywords_json="[]",
                        source_db="manual",
                        source_file_id="file-style",
                        markdown_source_file_id="file-style",
                        user_tags_json="[]",
                        reading_status="read",
                        metadata_completeness="partial",
                        dedup_key="style-entry",
                    ),
                    BibEntry(
                        id="entry-other-user",
                        owner_user_id=other_owner_id,
                        title="Private Writing",
                        authors_json=json.dumps(["宁健康"]),
                        year=2024,
                        journal="管理世界",
                        keywords_json="[]",
                        source_db="manual",
                        user_tags_json="[]",
                        reading_status="none",
                        metadata_completeness="partial",
                        dedup_key="other-style-entry",
                    ),
                ]
            )
            session.commit()
        return {"owner_id": owner_id, "entry_id": "entry-style"}

    def test_detect_style_focus_identifies_section_requests(self) -> None:
        self.assertEqual(detect_style_focus("帮我分析这篇论文的引言写作风格"), "introduction")
        self.assertEqual(detect_style_focus("theory derivation style"), "theory")
        self.assertEqual(detect_style_focus("method writing"), "method")
        self.assertEqual(detect_style_focus("整体论证风格"), "general")

    def test_extract_style_sections_returns_heading_bounded_sections(self) -> None:
        text = "# Introduction\nIntro text.\n# Theory\nTheory text.\n# Methods\nMethod text.\n"
        sections = extract_style_sections(text, "theory", max_sections=2)

        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["heading_path"], "Theory")
        self.assertIn("Theory text", sections[0]["quote"])
        self.assertNotIn("Method text", sections[0]["quote"])

    def test_analyze_writing_style_returns_p0_sections_for_matching_author(self) -> None:
        ids = self.seed_library()

        async def run():
            async with self.AsyncSessionLocal() as session:
                return await analyze_writing_style(
                    session,
                    owner_user_id=int(ids["owner_id"]),
                    question="帮我分析宁健康这篇论文的引言写作风格",
                    author_or_journal="宁健康",
                    section_type="introduction",
                    limit_entries=5,
                    max_sections_per_entry=2,
                )

        result = asyncio.run(run())
        self.assertEqual(result["style_focus"], "introduction")
        self.assertEqual([entry["entry_id"] for entry in result["entries"]], [ids["entry_id"]])
        self.assertEqual(result["style_evidence"][0]["source_tier"], "P0")
        self.assertEqual(result["style_evidence"][0]["source_kind"], "style_evidence")
        self.assertEqual(result["style_evidence"][0]["section_type"], "introduction")
        self.assertIn("现实张力", result["style_evidence"][0]["quote"])
        self.assertTrue(result["analysis_instructions"])
        self.assertIn("未联网", "".join(result["limitations"]))


if __name__ == "__main__":
    unittest.main()
