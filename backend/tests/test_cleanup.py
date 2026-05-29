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

from cleanup import cleanup_expired, cleanup_normal_user_data, get_cleanup_log_path  # noqa: E402
from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import (  # noqa: E402
    AgentActionProposal,
    AgentMessage,
    AgentSession,
    Artifact,
    BibEntry,
    BibReference,
    BibReferenceCitation,
    CardNote,
    DimensionItem,
    DimensionSet,
    File,
    Job,
    PromptTemplate,
    ReadingItem,
    ReadingItemEdit,
    RefFormatPreset,
    UploadBatch,
    User,
)


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

    def create_normal_cleanup_graph(
        self,
        normal_user_id: int,
        other_user_id: int,
    ) -> dict[str, str]:
        file_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        bib_id = str(uuid.uuid4())
        reference_id = str(uuid.uuid4())
        foreign_reference_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        proposal_id = str(uuid.uuid4())
        card_id = str(uuid.uuid4())
        upload_path = TEST_UPLOAD_ROOT / str(normal_user_id) / "normal.pdf"
        artifact_path = TEST_RESULTS_ROOT / str(normal_user_id) / job_id / "reading.md"
        card_path = TEST_RESULTS_ROOT / str(normal_user_id) / "cards" / "card-note.md"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        card_path.parent.mkdir(parents=True, exist_ok=True)
        upload_path.write_bytes(b"pdf-data")
        artifact_path.write_text("# reading", encoding="utf-8")
        card_path.write_text("# card", encoding="utf-8")

        with Session(self.sync_engine) as session:
            batch = UploadBatch(
                id=str(uuid.uuid4()),
                owner_user_id=normal_user_id,
                source_type="single",
                total_files=1,
                succeeded=1,
                failed=0,
                status="success",
                expires_at=None,
            )
            file_record = File(
                id=file_id,
                owner_user_id=normal_user_id,
                original_name="normal.pdf",
                file_type="pdf",
                storage_path=upload_path.as_posix(),
                size_bytes=8,
                md5=f"md5-{normal_user_id}",
                expires_at=None,
            )
            job = Job(
                id=job_id,
                owner_user_id=normal_user_id,
                job_type="reading_long",
                status="success",
                input_file_id=file_id,
                params_json="{}",
                progress=100,
                current_stage="完成",
                expires_at=None,
            )
            bib = BibEntry(
                id=bib_id,
                owner_user_id=normal_user_id,
                title="Normal Paper",
                authors_json='["Alice"]',
                source_db="manual",
                reading_status="read",
                dedup_key=f"dedup-{normal_user_id}",
                source_file_id=file_id,
                metadata_completeness="full",
                expires_at=None,
            )
            artifact = Artifact(
                job_id=job_id,
                owner_user_id=normal_user_id,
                artifact_type="reading_final",
                filename="reading.md",
                storage_path=f"{normal_user_id}/{job_id}/reading.md",
                size_bytes=9,
                expires_at=None,
            )
            reading_item = ReadingItem(
                owner_user_id=normal_user_id,
                bib_entry_id=bib_id,
                job_id=job_id,
                mode="long",
                section_type="dimension",
                item_key="summary",
                item_label="Summary",
                content="content",
            )
            session.add_all([batch, file_record, job, bib, artifact, reading_item])
            session.flush()

            session.add(
                ReadingItemEdit(
                    reading_item_id=reading_item.id,
                    owner_user_id=normal_user_id,
                    edited_content="edited",
                )
            )
            session.add(
                CardNote(
                    id=card_id,
                    owner_user_id=normal_user_id,
                    source_bib_entry_id=bib_id,
                    source_version="translated",
                    source_markdown_file_id=file_id,
                    source_translation_artifact_id=artifact.id,
                    title="Card",
                    selected_text="snippet",
                    body_markdown="body",
                    storage_path=f"{normal_user_id}/cards/card-note.md",
                    expires_at=None,
                )
            )
            session.add(
                PromptTemplate(
                    owner_user_id=normal_user_id,
                    scope="user",
                    prompt_type="translation",
                    prompt_key="default",
                    title="Prompt",
                    content="Prompt content",
                )
            )
            session.add(
                RefFormatPreset(
                    owner_user_id=normal_user_id,
                    name="GB/T",
                    format_rules="rules",
                )
            )
            dim_set = DimensionSet(
                owner_user_id=normal_user_id,
                name="My dims",
                description="desc",
            )
            session.add(dim_set)
            session.flush()
            session.add(
                DimensionItem(
                    set_id=dim_set.id,
                    dim_key="k1",
                    dim_name="Dimension 1",
                )
            )
            session.add(
                AgentSession(
                    id=session_id,
                    owner_user_id=normal_user_id,
                    title="Agent chat",
                    status="active",
                )
            )
            session.add(
                AgentMessage(
                    id=message_id,
                    session_id=session_id,
                    owner_user_id=normal_user_id,
                    role="user",
                    event_type="message",
                    content="hello",
                    sort_order=1,
                )
            )
            session.add(
                AgentActionProposal(
                    id=proposal_id,
                    session_id=session_id,
                    owner_user_id=normal_user_id,
                    action_type="external_read",
                    status="pending",
                )
            )
            session.add(
                BibReference(
                    id=reference_id,
                    owner_user_id=normal_user_id,
                    source_bib_entry_id=bib_id,
                    source_job_id=job_id,
                    reference_order=1,
                    raw_text="Normal ref",
                    authors_json="[]",
                )
            )
            session.add(
                BibReferenceCitation(
                    id=str(uuid.uuid4()),
                    owner_user_id=normal_user_id,
                    source_bib_entry_id=bib_id,
                    bib_reference_id=reference_id,
                    source_job_id=job_id,
                    quote_text="citation",
                )
            )
            other_bib = BibEntry(
                id=str(uuid.uuid4()),
                owner_user_id=other_user_id,
                title="Other Paper",
                authors_json='["Bob"]',
                source_db="manual",
                reading_status="none",
                dedup_key=f"dedup-{other_user_id}",
                metadata_completeness="full",
                expires_at=None,
            )
            session.add(other_bib)
            session.flush()
            session.add(
                BibReference(
                    id=foreign_reference_id,
                    owner_user_id=other_user_id,
                    source_bib_entry_id=other_bib.id,
                    reference_order=2,
                    raw_text="Foreign ref",
                    authors_json="[]",
                    matched_bib_entry_id=bib_id,
                    match_method="dedup",
                    match_score=0.95,
                )
            )
            session.commit()

        return {
            "upload_path": upload_path.as_posix(),
            "artifact_path": artifact_path.as_posix(),
            "card_path": card_path.as_posix(),
            "foreign_reference_id": foreign_reference_id,
        }

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

    def test_cleanup_normal_user_data_clears_cross_user_matches_and_deletes_owned_records(self) -> None:
        normal_user_id = self.create_user("alice", role="normal")
        vip_user_id = self.create_user("vipuser", role="vip")
        graph = self.create_normal_cleanup_graph(normal_user_id, vip_user_id)

        result = asyncio.run(cleanup_normal_user_data(dry_run=False))
        self.assertEqual(result["users_affected"], 1)
        self.assertGreaterEqual(result["bib_reference_matches_cleared"], 1)

        self.assertFalse(Path(graph["upload_path"]).exists())
        self.assertFalse(Path(graph["artifact_path"]).exists())
        self.assertFalse(Path(graph["card_path"]).exists())

        with Session(self.sync_engine) as session:
            self.assertEqual(session.query(File).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(Artifact).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(CardNote).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(Job).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(BibEntry).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(UploadBatch).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(BibReference).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(
                session.query(BibReferenceCitation).filter_by(owner_user_id=normal_user_id).count(), 0
            )
            self.assertEqual(session.query(PromptTemplate).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(RefFormatPreset).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(DimensionSet).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(DimensionItem).count(), 0)
            self.assertEqual(session.query(AgentSession).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(AgentMessage).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(
                session.query(AgentActionProposal).filter_by(owner_user_id=normal_user_id).count(), 0
            )
            self.assertEqual(session.query(ReadingItem).filter_by(owner_user_id=normal_user_id).count(), 0)
            self.assertEqual(session.query(ReadingItemEdit).filter_by(owner_user_id=normal_user_id).count(), 0)

            foreign_ref = session.query(BibReference).filter_by(id=graph["foreign_reference_id"]).one()
            self.assertIsNone(foreign_ref.matched_bib_entry_id)
            self.assertEqual(foreign_ref.owner_user_id, vip_user_id)


if __name__ == "__main__":
    unittest.main()
