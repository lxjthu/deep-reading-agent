from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-data-portability-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_data_portability.sqlite"
TEST_UPLOAD_ROOT = Path(TEMP_DIR) / "_uploads"
TEST_RESULTS_ROOT = Path(TEMP_DIR) / "results"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["UPLOAD_ROOT_DIR"] = TEST_UPLOAD_ROOT.as_posix()
os.environ["RESULTS_ROOT_DIR"] = TEST_RESULTS_ROOT.as_posix()
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

from db import AsyncSessionLocal, Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import BibEntry, File, PromptTemplate, UploadBatch, User  # noqa: E402
from services.data_portability import (  # noqa: E402
    IMPORT_MODE_APPEND,
    IMPORT_MODE_REPLACE,
    import_user_data,
)
from upload_storage import build_storage_path  # noqa: E402


class DataPortabilityTests(unittest.TestCase):
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
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    def create_user(self, username: str, role: str = "vip") -> int:
        with Session(self.sync_engine) as session:
            user = User(
                username=username,
                email=f"{username}@example.com",
                password_hash="hashed",
                role=role,
                is_active=1,
                token_version=0,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user.id

    async def run_import(self, user_id: int, dra_path: Path, mode: str) -> dict:
        async with AsyncSessionLocal() as session:
            user = await session.get(User, user_id)
            assert user is not None
            return await import_user_data(session, user, dra_path, mode=mode)

    def create_dra_package(
        self,
        *,
        schema_version: str = "006",
        tables: dict[str, list[dict]],
        files: dict[str, bytes] | None = None,
        artifacts: dict[tuple[str, str], bytes] | None = None,
        card_notes: dict[str, bytes] | None = None,
    ) -> Path:
        work_dir = Path(tempfile.mkdtemp(prefix="dra-test-pkg-", dir=TEMP_DIR))
        (work_dir / "data").mkdir(parents=True, exist_ok=True)
        (work_dir / "files").mkdir(parents=True, exist_ok=True)
        (work_dir / "artifacts").mkdir(parents=True, exist_ok=True)
        (work_dir / "card_notes").mkdir(parents=True, exist_ok=True)

        for table_name, rows in tables.items():
            (work_dir / "data" / f"{table_name}.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        for filename, payload in (files or {}).items():
            (work_dir / "files" / filename).write_bytes(payload)

        for (job_id, filename), payload in (artifacts or {}).items():
            job_dir = work_dir / "artifacts" / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / filename).write_bytes(payload)

        for card_id, payload in (card_notes or {}).items():
            (work_dir / "card_notes" / f"{card_id}.md").write_bytes(payload)

        manifest = {
            "format_version": 1,
            "exported_at": "2026-05-29T00:00:00",
            "source_host": "legacy-test",
            "schema_version": schema_version,
            "user": {"username": "legacy", "role": "vip", "email": "legacy@example.com"},
            "stats": {table_name: len(rows) for table_name, rows in tables.items()},
            "missing_files": [],
            "errors": [],
        }
        (work_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        fd, zip_name = tempfile.mkstemp(suffix=".dra", dir=TEMP_DIR)
        os.close(fd)
        zip_path = Path(zip_name)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in work_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(work_dir).as_posix())
        shutil.rmtree(work_dir, ignore_errors=True)
        return zip_path

    def test_append_mode_reuses_same_md5_file_and_same_bib_entry(self) -> None:
        user_id = self.create_user("append-user")
        existing_file_id = "existing-file"
        existing_bib_id = "existing-bib"
        file_path, storage_path = build_storage_path(user_id, existing_file_id, ".pdf")
        file_path.write_bytes(b"existing-pdf")

        with Session(self.sync_engine) as session:
            session.add(
                File(
                    id=existing_file_id,
                    owner_user_id=user_id,
                    original_name="paper.pdf",
                    file_type="pdf",
                    storage_path=storage_path,
                    size_bytes=11,
                    md5="same-md5",
                    batch_id=None,
                )
            )
            session.add(
                BibEntry(
                    id=existing_bib_id,
                    owner_user_id=user_id,
                    title="Reusable Paper",
                    authors_json="[]",
                    year=2024,
                    doi=None,
                    journal=None,
                    abstract=None,
                    keywords_json="[]",
                    source_db="manual",
                    source_filter_job_id=None,
                    source_file_id=existing_file_id,
                    markdown_source_file_id=None,
                    user_tags_json="[]",
                    user_note=None,
                    is_pinned=0,
                    reading_status="read",
                    metadata_completeness="full",
                    dedup_key="dedup:reusable-paper",
                )
            )
            session.commit()

        dra_path = self.create_dra_package(
            tables={
                "upload_batches": [
                    {
                        "id": "legacy-batch",
                        "owner_user_id": 999,
                        "source_type": "single",
                        "total_files": 1,
                        "succeeded": 1,
                        "failed": 0,
                        "status": "success",
                        "note": None,
                        "created_at": "2026-05-23T10:00:00",
                        "expires_at": None,
                    }
                ],
                "files": [
                    {
                        "id": "legacy-file",
                        "owner_user_id": 999,
                        "original_name": "paper.pdf",
                        "file_type": "pdf",
                        "storage_path": "_uploads/999/legacy-file.pdf",
                        "size_bytes": 11,
                        "md5": "same-md5",
                        "batch_id": "legacy-batch",
                        "created_at": "2026-05-23T10:00:00",
                        "expires_at": None,
                    }
                ],
                "bib_entries": [
                    {
                        "id": "legacy-bib",
                        "owner_user_id": 999,
                        "title": "Reusable Paper",
                        "authors_json": "[]",
                        "year": 2024,
                        "doi": None,
                        "journal": None,
                        "abstract": None,
                        "keywords_json": "[]",
                        "source_db": "manual",
                        "source_filter_job_id": None,
                        "source_file_id": "legacy-file",
                        "markdown_source_file_id": None,
                        "user_tags_json": "[]",
                        "user_note": None,
                        "is_pinned": 0,
                        "reading_status": "read",
                        "metadata_completeness": "full",
                        "dedup_key": "dedup:reusable-paper",
                        "created_at": "2026-05-23T10:00:00",
                        "updated_at": "2026-05-23T10:00:00",
                        "expires_at": None,
                    }
                ],
            },
            files={"legacy-file.pdf": b"existing-pdf"},
        )

        result = asyncio.run(self.run_import(user_id, dra_path, IMPORT_MODE_APPEND))
        self.assertEqual(result["mode"], IMPORT_MODE_APPEND)
        self.assertEqual(result["table_stats"]["files"]["reused"], 1)
        self.assertEqual(result["table_stats"]["bib_entries"]["reused"], 1)

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(File).count(), 1)
            self.assertEqual(session.query(BibEntry).count(), 1)

        dra_path.unlink(missing_ok=True)

    def test_replace_mode_updates_prompt_template_without_clearing_other_data(self) -> None:
        user_id = self.create_user("replace-user")
        with Session(self.sync_engine) as session:
            session.add_all(
                [
                    PromptTemplate(
                        owner_user_id=user_id,
                        scope="user",
                        prompt_type="long",
                        prompt_key="summary",
                        title="旧摘要模板",
                        content="old-content",
                        updated_by_user_id=user_id,
                    ),
                    PromptTemplate(
                        owner_user_id=user_id,
                        scope="user",
                        prompt_type="long",
                        prompt_key="outline",
                        title="保留模板",
                        content="keep-me",
                        updated_by_user_id=user_id,
                    ),
                ]
            )
            session.commit()

        dra_path = self.create_dra_package(
            tables={
                "prompt_templates": [
                    {
                        "id": 1,
                        "owner_user_id": 999,
                        "scope": "user",
                        "prompt_type": "long",
                        "prompt_key": "summary",
                        "title": "新摘要模板",
                        "content": "new-content",
                        "updated_by_user_id": 999,
                        "created_at": "2026-05-29T09:00:00",
                        "updated_at": "2026-05-29T09:00:00",
                    }
                ]
            },
        )

        result = asyncio.run(self.run_import(user_id, dra_path, IMPORT_MODE_REPLACE))
        self.assertEqual(result["table_stats"]["prompt_templates"]["replaced"], 1)

        with Session(self.sync_engine) as session:
            templates = session.execute(
                select(PromptTemplate).where(PromptTemplate.owner_user_id == user_id)
            ).scalars().all()
            self.assertEqual(len(templates), 2)
            summary = next(t for t in templates if t.prompt_key == "summary")
            outline = next(t for t in templates if t.prompt_key == "outline")
            self.assertEqual(summary.content, "new-content")
            self.assertEqual(summary.title, "新摘要模板")
            self.assertEqual(outline.content, "keep-me")

        dra_path.unlink(missing_ok=True)

    def test_legacy_package_with_missing_tables_is_accepted(self) -> None:
        user_id = self.create_user("legacy-user")
        dra_path = self.create_dra_package(
            schema_version="006",
            tables={
                "upload_batches": [],
                "files": [],
            },
        )

        result = asyncio.run(self.run_import(user_id, dra_path, IMPORT_MODE_APPEND))
        compat = result["compat"]
        self.assertTrue(compat["normalized_from_legacy"])
        self.assertTrue(compat["warnings"])
        self.assertEqual(result["mode"], IMPORT_MODE_APPEND)

        dra_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
