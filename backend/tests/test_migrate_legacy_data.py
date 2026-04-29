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

TEMP_DIR = tempfile.mkdtemp(prefix="dra-migrate-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_migrate.sqlite"
TEST_UPLOAD_ROOT = Path(TEMP_DIR) / "uploads"
TEST_RESULTS_ROOT = Path(TEMP_DIR) / "results"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["DEPLOY_SECRET"] = "test-deploy-secret"
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "30"
os.environ["UPLOAD_ROOT_DIR"] = TEST_UPLOAD_ROOT.as_posix()
os.environ["RESULTS_ROOT_DIR"] = TEST_RESULTS_ROOT.as_posix()

from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import Artifact, BibEntry, File, Job, User  # noqa: E402
from scripts import migrate_legacy_data as migrate_script  # noqa: E402


class MigrateLegacyDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())
        shutil.rmtree(TEMP_DIR, ignore_errors=True)

    def setUp(self) -> None:
        os.environ["UPLOAD_ROOT_DIR"] = TEST_UPLOAD_ROOT.as_posix()
        os.environ["RESULTS_ROOT_DIR"] = TEST_RESULTS_ROOT.as_posix()
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)
        shutil.rmtree(TEST_UPLOAD_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_RESULTS_ROOT, ignore_errors=True)
        TEST_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        TEST_RESULTS_ROOT.mkdir(parents=True, exist_ok=True)

    def test_migrate_legacy_upload_file_into_admin_storage(self) -> None:
        legacy_path = TEST_UPLOAD_ROOT / "yaojiaquan.pdf"
        legacy_path.write_bytes(b"%PDF-1.4 legacy pdf")

        stats = asyncio.run(migrate_script.migrate_legacy_data(dry_run=False))
        self.assertEqual(stats.migrated_uploads, 1)

        with Session(self.sync_engine) as session:
            admin = session.execute(select(User).where(User.username == "admin")).scalar_one()
            record = session.execute(select(File)).scalar_one()
            self.assertEqual(record.owner_user_id, admin.id)
            self.assertEqual(record.file_type, "pdf")
            migrated_path = Path(record.storage_path)
            if not migrated_path.is_absolute():
                migrated_path = PROJECT_ROOT / migrated_path
            self.assertTrue(migrated_path.exists())
            self.assertFalse(legacy_path.exists())
            self.assertIn(f"{admin.id}", migrated_path.as_posix())

    def test_migrate_legacy_results_into_jobs_and_artifacts(self) -> None:
        filter_dir = TEST_RESULTS_ROOT / "literature_filter"
        synthesis_dir = TEST_RESULTS_ROOT / "synthesis"
        reading_dir = TEST_RESULTS_ROOT / "legacy-paper"
        filter_dir.mkdir(parents=True, exist_ok=True)
        synthesis_dir.mkdir(parents=True, exist_ok=True)
        reading_dir.mkdir(parents=True, exist_ok=True)
        (filter_dir / "filtered_screened.xlsx").write_bytes(b"excel")
        (synthesis_dir / "synthesis_topic.md").write_text("# synthesis", encoding="utf-8")
        (reading_dir / "Step_1_notes.md").write_text("# step", encoding="utf-8")
        (reading_dir / "Final_Deep_Reading_Report.md").write_text("# final", encoding="utf-8")

        stats = asyncio.run(migrate_script.migrate_legacy_data(dry_run=False))
        self.assertEqual(stats.migrated_results, 4)

        with Session(self.sync_engine) as session:
            jobs = session.execute(select(Job)).scalars().all()
            artifacts = session.execute(select(Artifact)).scalars().all()
            self.assertEqual(len(jobs), 3)
            self.assertEqual(len(artifacts), 4)
            artifact_types = {artifact.artifact_type for artifact in artifacts}
            self.assertIn("filter_excel", artifact_types)
            self.assertIn("synthesis_md", artifact_types)
            self.assertIn("reading_step", artifact_types)
            self.assertIn("reading_final", artifact_types)
            for artifact in artifacts:
                self.assertTrue((TEST_RESULTS_ROOT / artifact.storage_path).exists())

    def test_migrate_legacy_pdf_creates_minimal_bib_entry(self) -> None:
        (TEST_UPLOAD_ROOT / "legacy-paper.pdf").write_bytes(b"%PDF-1.4 legacy pdf")

        asyncio.run(migrate_script.migrate_legacy_data(dry_run=False))

        with Session(self.sync_engine) as session:
            bib = session.execute(select(BibEntry)).scalar_one()
            self.assertEqual(bib.metadata_completeness, "minimal")
            self.assertEqual(bib.reading_status, "has_pdf")
            self.assertEqual(bib.source_db, "pdf_extracted")

    def test_migrate_legacy_dry_run_keeps_files_and_db_unchanged(self) -> None:
        legacy_upload = TEST_UPLOAD_ROOT / "legacy-paper.pdf"
        legacy_result_dir = TEST_RESULTS_ROOT / "synthesis"
        legacy_result_dir.mkdir(parents=True, exist_ok=True)
        legacy_upload.write_bytes(b"%PDF-1.4 legacy pdf")
        (legacy_result_dir / "legacy.md").write_text("# legacy", encoding="utf-8")

        stats = asyncio.run(migrate_script.migrate_legacy_data(dry_run=True))
        self.assertEqual(stats.migrated_uploads, 1)
        self.assertEqual(stats.migrated_results, 1)
        self.assertTrue(legacy_upload.exists())
        self.assertTrue((legacy_result_dir / "legacy.md").exists())

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(User).count(), 0)
            self.assertEqual(session.query(File).count(), 0)
            self.assertEqual(session.query(Job).count(), 0)
            self.assertEqual(session.query(Artifact).count(), 0)

    def test_migrate_skips_already_structured_paths(self) -> None:
        admin_dir = TEST_UPLOAD_ROOT / "1"
        results_dir = TEST_RESULTS_ROOT / "1" / "job-1"
        admin_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        (admin_dir / "existing.pdf").write_bytes(b"%PDF-1.4 existing")
        (results_dir / "final.md").write_text("# existing", encoding="utf-8")

        stats = asyncio.run(migrate_script.migrate_legacy_data(dry_run=False))
        self.assertEqual(stats.skipped_structured, 2)

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(File).count(), 0)
            self.assertEqual(session.query(Job).count(), 0)
            self.assertEqual(session.query(Artifact).count(), 0)


if __name__ == "__main__":
    unittest.main()
