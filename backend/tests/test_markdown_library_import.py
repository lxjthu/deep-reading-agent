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
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-md-library-import-")
TEST_DB_PATH = Path(TEMP_DIR) / "test.sqlite"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"

from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import BibEntry, File, User  # noqa: E402
from services.markdown_library_import import import_markdown_file_to_library  # noqa: E402


class MarkdownLibraryImportTests(unittest.TestCase):
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
        with Session(self.sync_engine) as session:
            session.add(
                User(
                    id=1,
                    username="alice",
                    email="alice@example.com",
                    password_hash="hash",
                    role="vip",
                    is_active=1,
                    token_version=0,
                )
            )
            session.commit()

    def write_markdown(self, file_id: str, body: str) -> Path:
        path = Path(TEMP_DIR) / f"{file_id}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def add_file(self, file_id: str, path: Path, original_name: str) -> None:
        with Session(self.sync_engine) as session:
            session.add(
                File(
                    id=file_id,
                    owner_user_id=1,
                    original_name=original_name,
                    file_type="markdown",
                    storage_path=path.as_posix(),
                    size_bytes=path.stat().st_size,
                    md5=f"md5-{file_id}",
                    expires_at=None,
                )
            )
            session.commit()

    def test_import_markdown_with_frontmatter_creates_library_entry(self) -> None:
        file_id = "file-md-1"
        path = self.write_markdown(
            file_id,
            """---
title: 数字乡村建设赋能森林生态产品价值实现：理论逻辑与实践路径
authors:
  - 张三
  - 李四
journal: 农业经济问题
year: 2024
doi: 10.1234/example
abstract: 摘要内容
keywords:
  - 数字乡村
  - 生态产品
start_page: 10
end_page: 18
---

# 正文
""",
        )
        self.add_file(file_id, path, "生态产品价值实现文献/数字乡村建设赋能森林生态产品价值实现_ocr.md")

        async def run() -> str | None:
            from db import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                record = await db.get(File, file_id)
                entry = await import_markdown_file_to_library(db, owner_user_id=1, record=record)
                await db.commit()
                return entry.id if entry else None

        entry_id = asyncio.run(run())
        self.assertIsNotNone(entry_id)
        with Session(self.sync_engine) as session:
            entry = session.get(BibEntry, entry_id)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual(entry.title, "数字乡村建设赋能森林生态产品价值实现：理论逻辑与实践路径")
            self.assertEqual(json.loads(entry.authors_json), ["张三", "李四"])
            self.assertEqual(entry.journal, "农业经济问题")
            self.assertEqual(entry.year, 2024)
            self.assertEqual(entry.doi, "10.1234/example")
            self.assertEqual(entry.pages, "10-18")
            self.assertEqual(entry.source_db, "md_extracted")
            self.assertEqual(entry.markdown_source_file_id, file_id)
            self.assertEqual(entry.reading_status, "has_pdf")

    def test_import_markdown_merges_duplicate_by_doi_without_overwriting(self) -> None:
        file_id = "file-md-2"
        path = self.write_markdown(
            file_id,
            """---
title: 数字乡村建设赋能森林生态产品价值实现：理论逻辑与实践路径
authors:
  - 新作者
journal: 新期刊
year: 2025
doi: 10.1234/example
abstract: 新摘要
---

# 正文
""",
        )
        self.add_file(file_id, path, "数字乡村建设赋能森林生态产品价值实现_ocr.md")
        with Session(self.sync_engine) as session:
            session.add(
                BibEntry(
                    id="entry-existing",
                    owner_user_id=1,
                    title="旧标题",
                    authors_json=json.dumps(["旧作者"], ensure_ascii=False),
                    year=2020,
                    doi="10.1234/example",
                    journal="旧期刊",
                    abstract=None,
                    keywords_json="[]",
                    venue_type=None,
                    citation_count=None,
                    source_db="manual",
                    source_filter_job_id=None,
                    source_file_id=None,
                    user_tags_json="[]",
                    user_note=None,
                    is_pinned=0,
                    reading_status="none",
                    metadata_completeness="partial",
                    dedup_key="doi:10.1234/example",
                    expires_at=None,
                )
            )
            session.commit()

        async def run() -> str | None:
            from db import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                record = await db.get(File, file_id)
                entry = await import_markdown_file_to_library(db, owner_user_id=1, record=record)
                await db.commit()
                return entry.id if entry else None

        entry_id = asyncio.run(run())
        self.assertEqual(entry_id, "entry-existing")
        with Session(self.sync_engine) as session:
            entries = session.execute(select(BibEntry)).scalars().all()
            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry.title, "旧标题")
            self.assertEqual(entry.journal, "旧期刊")
            self.assertEqual(entry.year, 2020)
            self.assertEqual(entry.abstract, "新摘要")
            self.assertEqual(entry.markdown_source_file_id, file_id)
            self.assertEqual(entry.source_file_id, file_id)
            self.assertEqual(entry.reading_status, "has_pdf")


if __name__ == "__main__":
    unittest.main()
