from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-cleanup-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_cleanup.sqlite"
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

from cleanup import cleanup_expired, get_cleanup_log_path  # noqa: E402
from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import Artifact, BibEntry, File, Job, UploadBatch, User  # noqa: E402


class CleanupTests(unittest.TestCase):
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
        log_path = get_cleanup_log_path()
        if log_path.exists():
            log_path.unlink()

    def create_user(self, username: str, *, role: str = "normal") -> int:
        with Session(self.sync_engine) as session:
            user = User(
                username=username,
                email=f"{username}@example.com",
                password_hash="hashed",
                role=role,
                is_active=1,
                token_version=0,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return user.id

    def create_owned_records(
        self,
        owner_user_id: int,
        *,
        expires_at: datetime | None,
        file_name: str = "paper.pdf",
        artifact_name: str = "final.md",
    ) -> tuple[str, str]:
        file_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        upload_path = TEST_UPLOAD_ROOT / str(owner_user_id) / file_name
        result_path = TEST_RESULTS_ROOT / str(owner_user_id) / job_id / artifact_name
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(b"pdf-data")
        result_path.write_text("# report", encoding="utf-8")

        with Session(self.sync_engine) as session:
            session.add(
                UploadBatch(
                    id=str(uuid.uuid4()),
                    owner_user_id=owner_user_id,
                    source_type="single",
                    total_files=1,
                    succeeded=1,
                    failed=0,
                    status="success",
                    expires_at=expires_at,
                )
            )
            session.add(
                File(
                    id=file_id,
                    owner_user_id=owner_user_id,
                    batch_id=None,
                    file_type="pdf",
                    original_name=file_name,
                    storage_path=upload_path.as_posix(),
                    size_bytes=8,
                    md5=f"md5-{owner_user_id}-{file_name}",
                    expires_at=expires_at,
                )
            )
            session.add(
                Job(
                    id=job_id,
                    owner_user_id=owner_user_id,
                    job_type="reading_long",
                    status="success",
                    input_file_id=file_id,
                    params_json="{}",
                    progress=100,
                    current_stage="完成",
                    expires_at=expires_at,
                )
            )
            session.add(
                BibEntry(
                    id=str(uuid.uuid4()),
                    owner_user_id=owner_user_id,
                    title="Sample Paper",
                    authors_json='["Alice"]',
                    source_db="manual",
                    reading_status="read",
                    dedup_key=f"dedup-{owner_user_id}-{file_name}",
                    source_file_id=file_id,
                    source_filter_job_id=None,
                    metadata_completeness="full",
                    expires_at=expires_at,
                )
            )
            session.add(
                Artifact(
                    job_id=job_id,
                    owner_user_id=owner_user_id,
                    artifact_type="reading_final",
                    filename=artifact_name,
                    storage_path=f"{owner_user_id}/{job_id}/{artifact_name}",
                    size_bytes=9,
                    expires_at=expires_at,
                )
            )
            session.commit()
        return upload_path.as_posix(), result_path.as_posix()

    def test_cleanup_dry_run_keeps_db_and_files(self) -> None:
        user_id = self.create_user("alice")
        expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        upload_path, result_path = self.create_owned_records(user_id, expires_at=expired_at)

        result = asyncio.run(cleanup_expired(now=datetime.now(UTC).replace(tzinfo=None), dry_run=True))
        self.assertTrue(result["dry_run"])
        self.assertTrue(Path(upload_path).exists())
        self.assertTrue(Path(result_path).exists())

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(File).count(), 1)
            self.assertEqual(session.query(Artifact).count(), 1)

    def test_cleanup_removes_expired_normal_user_data(self) -> None:
        user_id = self.create_user("alice")
        expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        upload_path, result_path = self.create_owned_records(user_id, expires_at=expired_at)

        result = asyncio.run(cleanup_expired(now=datetime.now(UTC).replace(tzinfo=None), dry_run=False))
        self.assertFalse(result["dry_run"])
        self.assertFalse(Path(upload_path).exists())
        self.assertFalse(Path(result_path).exists())

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(File).count(), 0)
            self.assertEqual(session.query(Artifact).count(), 0)
            self.assertEqual(session.query(Job).count(), 0)
            self.assertEqual(session.query(BibEntry).count(), 0)
            self.assertEqual(session.query(UploadBatch).count(), 0)

    def test_cleanup_keeps_non_expired_and_vip_admin_data(self) -> None:
        normal_id = self.create_user("alice", role="normal")
        vip_id = self.create_user("vipuser", role="vip")
        admin_id = self.create_user("rootadmin", role="admin")

        future = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2)
        self.create_owned_records(normal_id, expires_at=future, file_name="normal.pdf", artifact_name="normal.md")
        self.create_owned_records(vip_id, expires_at=None, file_name="vip.pdf", artifact_name="vip.md")
        self.create_owned_records(admin_id, expires_at=None, file_name="admin.pdf", artifact_name="admin.md")

        asyncio.run(cleanup_expired(now=datetime.now(UTC).replace(tzinfo=None), dry_run=False))

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(File).count(), 3)
            self.assertEqual(session.query(Artifact).count(), 3)
            owners = {row[0] for row in session.execute(select(File.owner_user_id)).all()}
            self.assertEqual(owners, {normal_id, vip_id, admin_id})

    def test_cleanup_removes_empty_user_directories(self) -> None:
        user_id = self.create_user("alice")
        expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        self.create_owned_records(user_id, expires_at=expired_at)

        asyncio.run(cleanup_expired(now=datetime.now(UTC).replace(tzinfo=None), dry_run=False))

        self.assertFalse((TEST_UPLOAD_ROOT / str(user_id)).exists())
        self.assertFalse((TEST_RESULTS_ROOT / str(user_id)).exists())


if __name__ == "__main__":
    unittest.main()
