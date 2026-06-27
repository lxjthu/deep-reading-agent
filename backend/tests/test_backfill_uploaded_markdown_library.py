from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_BASE = Path("C:/tmp")
TEMP_BASE.mkdir(parents=True, exist_ok=True)
TEMP_DIR = tempfile.mkdtemp(prefix="dra-md-backfill-tests-", dir=TEMP_BASE)
TEST_DB_PATH = Path(TEMP_DIR) / "test_backfill_md.sqlite"
TEST_UPLOADS_ROOT = Path(TEMP_DIR) / "uploads"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["UPLOADS_ROOT_DIR"] = TEST_UPLOADS_ROOT.as_posix()

from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import BibEntry, File, User  # noqa: E402
from scripts.backfill_uploaded_markdown_library import (  # noqa: E402
    ExistingEntry,
    FileCandidate,
    MarkdownMetadata,
    apply_plan,
    build_report,
    parse_markdown_metadata,
    plan_bindings,
)


def metadata(
    *,
    title: str = "生态产品价值实现路径研究",
    authors: list[str] | None = None,
    year: int | None = 2024,
    doi: str | None = "https://doi.org/10.1234/example",
) -> MarkdownMetadata:
    return MarkdownMetadata(
        title=title,
        authors=authors or ["张三", "李四"],
        year=year,
        doi="10.1234/example" if doi else None,
        journal="测试期刊",
        abstract="这是一段摘要。",
        keywords=["生态产品", "价值实现"],
        volume=None,
        issue="4",
        pages="13-24",
        source_file="paper.pdf",
        raw={},
    )


def candidate(
    file_id: str,
    *,
    meta: MarkdownMetadata | None = None,
    size: int = 100,
    original_name: str | None = None,
) -> FileCandidate:
    item_meta = meta or metadata()
    return FileCandidate(
        id=file_id,
        original_name=original_name or f"{item_meta.title}_ocr.md",
        storage_path=f"_uploads/1/{file_id}.md",
        size_bytes=size,
        expires_at=None,
        created_at=datetime(2026, 6, 27, 14, 40, 0),
        metadata=item_meta,
    )


def existing(
    entry_id: str,
    *,
    title: str = "生态产品价值实现路径研究",
    authors: list[str] | None = None,
    year: int | None = 2024,
    doi: str | None = "10.1234/example",
    markdown_source_file_id: str | None = None,
    dedup_key: str = "doi:10.1234/example",
) -> ExistingEntry:
    return ExistingEntry(
        id=entry_id,
        title=title,
        authors=authors or ["张三", "李四"],
        year=year,
        doi=doi,
        journal="测试期刊",
        abstract=None,
        volume=None,
        issue=None,
        pages=None,
        source_file_id=None,
        markdown_source_file_id=markdown_source_file_id,
        reading_status="none",
        dedup_key=dedup_key,
    )


class BackfillUploadedMarkdownLibraryTests(unittest.TestCase):
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
        shutil.rmtree(TEST_UPLOADS_ROOT, ignore_errors=True)
        TEST_UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)

    def test_parse_markdown_metadata_frontmatter(self) -> None:
        path = Path(TEMP_DIR) / "paper.md"
        path.write_text(
            """---
title: 高等教育高质量发展赋能共同富裕：内在机理与实践策略
authors:
  - 陈亮
  - 叶明裕
journal: 大学教育科学
year: 2024
issue: 4
start_page: 13
end_page: 24
doi: https://doi.org/10.3969/j.issn.1672-0717.2024.04.02
abstract: 摘要内容
tags:
  - 共同富裕
source_file: paper.pdf
---

# 正文
""",
            encoding="utf-8",
        )

        parsed = parse_markdown_metadata(path, "folder/original_ocr.md")

        self.assertEqual(parsed.title, "高等教育高质量发展赋能共同富裕：内在机理与实践策略")
        self.assertEqual(parsed.authors, ["陈亮", "叶明裕"])
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.doi, "10.3969/j.issn.1672-0717.2024.04.02")
        self.assertEqual(parsed.pages, "13-24")
        self.assertEqual(parsed.keywords, ["共同富裕"])
        self.assertEqual(parsed.source_file, "paper.pdf")

    def test_parse_markdown_metadata_falls_back_to_filename(self) -> None:
        path = Path(TEMP_DIR) / "plain.md"
        path.write_text("# 正文", encoding="utf-8")

        parsed = parse_markdown_metadata(path, "生态产品价值实现文献/长江经济带生态产品价值实现路径研究_ocr.md")

        self.assertEqual(parsed.title, "长江经济带生态产品价值实现路径研究")
        self.assertEqual(parsed.authors, [])

    def test_plan_prefers_doi_match(self) -> None:
        plan = plan_bindings([candidate("file-1")], [existing("entry-1", title="完全不同标题")])

        self.assertEqual(plan.decisions[0].decision, "link_existing")
        self.assertEqual(plan.decisions[0].matched_entry_id, "entry-1")
        self.assertEqual(plan.decisions[0].match_method, "doi")

    def test_plan_uses_exact_title_when_doi_absent(self) -> None:
        meta = metadata(doi=None)
        plan = plan_bindings(
            [candidate("file-1", meta=meta)],
            [existing("entry-1", doi=None, dedup_key="sig:other:2024:other")],
        )

        self.assertEqual(plan.decisions[0].decision, "link_existing")
        self.assertEqual(plan.decisions[0].match_method, "title_exact")

    def test_plan_uses_high_title_with_author_and_year(self) -> None:
        meta = metadata(title="生态产品价值实现路径研究：来自长江经济带的证据", doi=None)
        plan = plan_bindings(
            [candidate("file-1", meta=meta)],
            [
                existing(
                    "entry-1",
                    title="生态产品价值实现路径研究来自长江经济带的证据",
                    doi=None,
                    dedup_key="sig:other:2024:other",
                )
            ],
        )

        self.assertEqual(plan.decisions[0].decision, "link_existing")
        self.assertEqual(plan.decisions[0].match_method, "title_high")

    def test_plan_creates_entry_when_no_match(self) -> None:
        plan = plan_bindings([candidate("file-1")], [])

        self.assertEqual(plan.decisions[0].decision, "create_entry")
        self.assertEqual(plan.summary()["would_create_entries"], 1)

    def test_plan_skips_duplicate_markdown_candidate(self) -> None:
        weak = metadata(abstract=None)
        strong = metadata()
        plan = plan_bindings(
            [
                candidate("file-small", meta=weak, size=10),
                candidate("file-large", meta=strong, size=1000),
            ],
            [],
        )

        decisions = {d.file_id: d.decision for d in plan.decisions}
        self.assertEqual(decisions["file-large"], "create_entry")
        self.assertEqual(decisions["file-small"], "duplicate_markdown_candidate")

    def test_report_contains_dry_run_counts(self) -> None:
        plan = plan_bindings([candidate("file-1")], [])
        report = build_report(plan, applied=False)

        self.assertEqual(report["summary"]["candidate_files"], 1)
        self.assertEqual(report["summary"]["would_create_entries"], 1)
        self.assertEqual(report["summary"]["applied"], 0)
        self.assertEqual(report["decisions"][0]["decision"], "create_entry")

    def test_apply_creates_library_entry_from_existing_file(self) -> None:
        file_id = "file-1"
        meta = metadata()
        plan = plan_bindings([candidate(file_id, meta=meta)], [])

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
            session.add(
                File(
                    id=file_id,
                    owner_user_id=1,
                    original_name="生态产品价值实现路径研究_ocr.md",
                    file_type="markdown",
                    storage_path="_uploads/1/file-1.md",
                    size_bytes=100,
                    md5="md5",
                    expires_at=None,
                )
            )
            session.commit()

        asyncio.run(apply_plan(1, [candidate(file_id, meta=meta)], plan))

        with Session(self.sync_engine) as session:
            entry = session.execute(select(BibEntry)).scalar_one()
            self.assertEqual(entry.title, meta.title)
            self.assertEqual(json.loads(entry.authors_json), meta.authors)
            self.assertEqual(entry.source_db, "md_extracted")
            self.assertEqual(entry.source_file_id, file_id)
            self.assertEqual(entry.markdown_source_file_id, file_id)
            self.assertEqual(entry.reading_status, "has_pdf")

    def test_apply_links_existing_entry_without_overwriting_metadata(self) -> None:
        file_id = "file-1"
        meta = metadata(abstract="新摘要")
        entry_id = "entry-1"
        plan = plan_bindings(
            [candidate(file_id, meta=meta)],
            [existing(entry_id, abstract=None, markdown_source_file_id=None)],
        )

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
            session.add(
                File(
                    id=file_id,
                    owner_user_id=1,
                    original_name="生态产品价值实现路径研究_ocr.md",
                    file_type="markdown",
                    storage_path="_uploads/1/file-1.md",
                    size_bytes=100,
                    md5="md5",
                    expires_at=None,
                )
            )
            session.add(
                BibEntry(
                    id=entry_id,
                    owner_user_id=1,
                    title="生态产品价值实现路径研究",
                    authors_json=json.dumps(["张三"], ensure_ascii=False),
                    year=2024,
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

        asyncio.run(apply_plan(1, [candidate(file_id, meta=meta)], plan))

        with Session(self.sync_engine) as session:
            entry = session.get(BibEntry, entry_id)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertEqual(entry.journal, "旧期刊")
            self.assertEqual(entry.abstract, "新摘要")
            self.assertEqual(entry.markdown_source_file_id, file_id)
            self.assertEqual(entry.source_file_id, file_id)
            self.assertEqual(entry.reading_status, "has_pdf")

