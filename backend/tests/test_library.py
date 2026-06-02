from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-library-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_library.sqlite"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["UPLOAD_ROOT_DIR"] = str((Path(TEMP_DIR) / "_uploads").resolve())
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("REFRESH_TOKEN_EXPIRE_DAYS", "30")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from db import Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import Artifact, BibEntry, BibReference, File, Job, JobBibEntry, UploadBatch, User  # noqa: E402
from routers import auth as auth_router  # noqa: E402
from routers import agent as agent_router  # noqa: E402
from routers import library as library_router  # noqa: E402
from upload_storage import build_storage_path  # noqa: E402


class LibraryRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = FastAPI()
        app.include_router(auth_router.router, prefix="/api/auth", tags=["Auth"])
        app.include_router(agent_router.router, prefix="/api/agent", tags=["Agent"])
        app.include_router(library_router.router, prefix="/api/library", tags=["Library"])
        cls.client = TestClient(app)
        cls.sync_engine = create_engine(SYNC_DATABASE_URL)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        cls.sync_engine.dispose()
        asyncio.run(async_engine.dispose())

    def setUp(self) -> None:
        Base.metadata.drop_all(self.sync_engine)
        Base.metadata.create_all(self.sync_engine)

    def register(self, username: str, password: str = "pwd12345") -> int:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password, "email": f"{username}@example.com"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.sync_engine) as session:
            user = session.execute(select(User).where(User.username == username)).scalar_one()
            return user.id

    def login_headers(self, username: str, password: str = "pwd12345") -> dict[str, str]:
        response = self.client.post("/api/auth/login", data={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def create_entry_with_timeline(self, owner_user_id: int, *, title: str = "Sample Paper") -> tuple[str, str]:
        file_id = str(uuid.uuid4())
        bib_id = str(uuid.uuid4())
        job_id = str(uuid.uuid4())
        file_path, storage_path = build_storage_path(owner_user_id, file_id, ".pdf")
        file_path.write_bytes(b"%PDF-1.4 sample")
        with Session(self.sync_engine) as session:
            session.add(
                File(
                    id=file_id,
                    owner_user_id=owner_user_id,
                    original_name="sample.pdf",
                    file_type="pdf",
                    storage_path=storage_path,
                    size_bytes=42,
                    md5=f"md5-{owner_user_id}-{title}",
                    batch_id=None,
                )
            )
            session.add(
                BibEntry(
                    id=bib_id,
                    owner_user_id=owner_user_id,
                    title=title,
                    authors_json=json.dumps(["Alice", "Bob"], ensure_ascii=False),
                    year=2024,
                    doi="10.1000/test",
                    journal="Journal of Testing",
                    abstract="Abstract body",
                    keywords_json=json.dumps(["test", "library"], ensure_ascii=False),
                    source_db="wos",
                    source_filter_job_id=None,
                    source_file_id=file_id,
                    user_tags_json=json.dumps(["important"], ensure_ascii=False),
                    user_note="Original note",
                    is_pinned=0,
                    reading_status="read",
                    metadata_completeness="partial",
                    dedup_key=f"title:{title.lower()}",
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
                    created_at=datetime.now(UTC).replace(tzinfo=None),
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            session.add(
                JobBibEntry(job_id=job_id, bib_entry_id=bib_id, role="target", sort_order=0)
            )
            session.add(
                Artifact(
                    job_id=job_id,
                    owner_user_id=owner_user_id,
                    artifact_type="reading_final",
                    filename="final.md",
                    storage_path=f"{owner_user_id}/{job_id}/final.md",
                    size_bytes=128,
                )
            )
            session.commit()
        return bib_id, job_id

    def attach_filter_evaluation(self, owner_user_id: int, bib_id: str, *, title: str = "Sample Paper") -> str:
        filter_job_id = str(uuid.uuid4())
        filter_path = PROJECT_ROOT / "deep_reading_results" / str(owner_user_id) / filter_job_id
        filter_path.mkdir(parents=True, exist_ok=True)
        excel_path = filter_path / "filtered_explorer.xlsx"
        pd.DataFrame(
            [
                {
                    "Title": title,
                    "DOI": "10.1000/test",
                    "Abstract": "Abstract body",
                    "abstract_cn": "这是摘要翻译",
                    "score": 92.5,
                    "reason": "high relevance",
                }
            ]
        ).to_excel(excel_path, index=False)

        with Session(self.sync_engine) as session:
            session.add(
                Job(
                    id=filter_job_id,
                    owner_user_id=owner_user_id,
                    job_type="filter",
                    status="success",
                    params_json="{}",
                    progress=100,
                    current_stage="完成",
                    created_at=datetime.now(UTC).replace(tzinfo=None),
                    finished_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            session.add(
                Artifact(
                    job_id=filter_job_id,
                    owner_user_id=owner_user_id,
                    artifact_type="filter_excel",
                    filename="filtered_explorer.xlsx",
                    storage_path=f"{owner_user_id}/{filter_job_id}/filtered_explorer.xlsx",
                    size_bytes=excel_path.stat().st_size,
                )
            )
            from db.models import BibFilterLink

            session.add(
                BibFilterLink(
                    bib_entry_id=bib_id,
                    filter_job_id=filter_job_id,
                    passed=1,
                    score=92.5,
                    reason="high relevance",
                )
            )
            session.commit()
        return filter_job_id

    def test_library_list_requires_authentication(self) -> None:
        response = self.client.get("/api/library/entries")
        self.assertEqual(response.status_code, 401, response.text)

    def test_agent_folder_upload_persists_batch_file_and_binds_matching_entry(self) -> None:
        user_id = self.register("agent-folder")
        headers = self.login_headers("agent-folder")
        bib_id = str(uuid.uuid4())
        with Session(self.sync_engine) as session:
            session.add(
                BibEntry(
                    id=bib_id,
                    owner_user_id=user_id,
                    title="Ecological Product Value",
                    source_db="manual",
                    dedup_key="title:ecological product value",
                )
            )
            session.commit()

        response = self.client.post(
            "/api/agent/inbox/upload-folder",
            headers=headers,
            files=[
                (
                    "files",
                    (
                        "folder/Ecological Product Value.md",
                        b"# Ecological Product Value\n\nsample",
                        "text/markdown",
                    ),
                )
            ],
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["succeeded"], 1, data)
        self.assertEqual(data["failed"], 0, data)
        self.assertEqual(data["results"][0]["matched_bib_entry_id"], bib_id, data)

        with Session(self.sync_engine) as session:
            batch = session.get(UploadBatch, data["batch_id"])
            self.assertIsNotNone(batch)
            uploaded = session.execute(select(File).where(File.batch_id == data["batch_id"])).scalar_one()
            entry = session.get(BibEntry, bib_id)
            self.assertEqual(uploaded.owner_user_id, user_id)
            self.assertEqual(entry.markdown_source_file_id, uploaded.id)

    def test_library_list_only_returns_current_user_entries(self) -> None:
        alice_id = self.register("alice")
        bob_id = self.register("bob")
        self.create_entry_with_timeline(alice_id, title="Alice Paper")
        self.create_entry_with_timeline(bob_id, title="Bob Paper")

        response = self.client.get("/api/library/entries", headers=self.login_headers("alice"))
        self.assertEqual(response.status_code, 200, response.text)
        titles = [item["title"] for item in response.json()]
        self.assertEqual(titles, ["Alice Paper"])

    def test_library_list_supports_journal_filter(self) -> None:
        alice_id = self.register("alice")
        self.create_entry_with_timeline(alice_id, title="Policy Paper")
        with Session(self.sync_engine) as session:
            entry = session.execute(select(BibEntry).where(BibEntry.owner_user_id == alice_id)).scalar_one()
            entry.journal = "American Economic Review"
            session.commit()

        response = self.client.get(
            "/api/library/entries?journal=Economic",
            headers=self.login_headers("alice"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()), 1)

    def test_library_page_returns_total_and_slice(self) -> None:
        alice_id = self.register("alice")
        for index in range(3):
            self.create_entry_with_timeline(alice_id, title=f"Paper {index}")

        response = self.client.get(
            "/api/library/entries/page?page=1&page_size=2",
            headers=self.login_headers("alice"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total"], 3)
        self.assertEqual(body["page"], 1)
        self.assertEqual(body["page_size"], 2)
        self.assertTrue(body["has_more"])
        self.assertEqual(len(body["items"]), 2)

    def test_library_detail_includes_timeline_and_artifacts(self) -> None:
        alice_id = self.register("alice")
        bib_id, job_id = self.create_entry_with_timeline(alice_id)
        self.attach_filter_evaluation(alice_id, bib_id)

        response = self.client.get(f"/api/library/entries/{bib_id}", headers=self.login_headers("alice"))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["id"], bib_id)
        self.assertEqual(body["source_file_name"], "sample.pdf")
        self.assertEqual(len(body["timeline"]), 1)
        self.assertEqual(body["timeline"][0]["job_id"], job_id)
        self.assertEqual(body["timeline"][0]["artifacts"][0]["filename"], "final.md")
        self.assertEqual(body["filter_evaluations"][0]["score"], 92.5)
        self.assertEqual(body["filter_evaluations"][0]["reason"], "high relevance")
        self.assertEqual(body["filter_evaluations"][0]["abstract_translation"], "这是摘要翻译")

    def test_apply_online_match_merges_existing_duplicate_dedup_key(self) -> None:
        alice_id = self.register("alice")
        headers = self.login_headers("alice")
        current_id = str(uuid.uuid4())
        duplicate_id = str(uuid.uuid4())
        file_id = str(uuid.uuid4())

        with Session(self.sync_engine) as session:
            session.add(
                File(
                    id=file_id,
                    owner_user_id=alice_id,
                    original_name="current.pdf",
                    file_type="pdf",
                    storage_path=f"{alice_id}/{file_id}/current.pdf",
                    size_bytes=42,
                    md5="md5-current",
                    batch_id=None,
                )
            )
            session.add(
                BibEntry(
                    id=current_id,
                    owner_user_id=alice_id,
                    title="Current Upload",
                    authors_json="[]",
                    year=None,
                    doi=None,
                    journal=None,
                    abstract=None,
                    keywords_json="[]",
                    source_db="pdf_extracted",
                    source_filter_job_id=None,
                    source_file_id=file_id,
                    user_tags_json="[]",
                    is_pinned=0,
                    reading_status="has_pdf",
                    metadata_completeness="minimal",
                    dedup_key="title:current upload",
                )
            )
            session.add(
                BibEntry(
                    id=duplicate_id,
                    owner_user_id=alice_id,
                    title="Existing Metadata",
                    authors_json=json.dumps(["Abdelaziz Lawani"], ensure_ascii=False),
                    year=2025,
                    doi="10.1002/agr.70025",
                    journal="Agribusiness",
                    abstract="Existing abstract",
                    keywords_json="[]",
                    source_db="other",
                    source_filter_job_id=None,
                    source_file_id=None,
                    user_tags_json="[]",
                    is_pinned=0,
                    reading_status="none",
                    metadata_completeness="partial",
                    dedup_key="doi:10.1002/agr.70025",
                )
            )
            session.add(
                BibReference(
                    id=str(uuid.uuid4()),
                    owner_user_id=alice_id,
                    source_bib_entry_id=current_id,
                    source_job_id=None,
                    reference_order=1,
                    raw_text="Lawani A. Existing Metadata.",
                    authors_json=json.dumps(["Abdelaziz Lawani"], ensure_ascii=False),
                    year=2025,
                    title="Existing Metadata",
                    journal="Agribusiness",
                    doi="10.1002/agr.70025",
                    dedup_key="doi:10.1002/agr.70025",
                    matched_bib_entry_id=duplicate_id,
                    match_method="doi",
                    match_score=1.0,
                )
            )
            session.commit()

        response = self.client.post(
            f"/api/library/entries/{current_id}/apply-match",
            headers=headers,
            json={
                "candidate": {
                    "title": "Existing Metadata",
                    "authors": ["Abdelaziz Lawani"],
                    "year": 2025,
                    "journal": "Agribusiness",
                    "doi": "10.1002/agr.70025",
                    "volume": None,
                    "issue": None,
                    "pages": None,
                    "source": "crossref",
                    "score": 0.95,
                }
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.sync_engine) as session:
            entries = session.execute(select(BibEntry).where(BibEntry.owner_user_id == alice_id)).scalars().all()
            self.assertEqual(len(entries), 1)
            merged = entries[0]
            self.assertEqual(merged.id, current_id)
            self.assertEqual(merged.dedup_key, "doi:10.1002/agr.70025")
            self.assertEqual(merged.source_file_id, file_id)
            ref = session.execute(select(BibReference).where(BibReference.owner_user_id == alice_id)).scalar_one()
            self.assertEqual(ref.source_bib_entry_id, current_id)
            self.assertEqual(ref.matched_bib_entry_id, current_id)

    def test_library_detail_clears_missing_source_file_reference(self) -> None:
        alice_id = self.register("alice")
        bib_id, _job_id = self.create_entry_with_timeline(alice_id)
        with Session(self.sync_engine) as session:
            entry = session.execute(select(BibEntry).where(BibEntry.id == bib_id)).scalar_one()
            file_record = session.execute(select(File).where(File.id == entry.source_file_id)).scalar_one()
            missing_path = Path(file_record.storage_path)
            if not missing_path.is_absolute():
                missing_path = PROJECT_ROOT / missing_path
            missing_path.unlink()

        response = self.client.get(f"/api/library/entries/{bib_id}", headers=self.login_headers("alice"))
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIsNone(body["source_file_id"])
        self.assertIsNone(body["source_file_name"])

        with Session(self.sync_engine) as session:
            entry = session.execute(select(BibEntry).where(BibEntry.id == bib_id)).scalar_one()
            self.assertIsNone(entry.source_file_id)

    def test_markdown_upload_recreates_missing_deduped_file(self) -> None:
        alice_id = self.register("alice")
        bib_id, _job_id = self.create_entry_with_timeline(alice_id)
        content = b"# Original Markdown\n\nBody"
        md5_hash = hashlib.md5(content).hexdigest()
        stale_file_id = str(uuid.uuid4())
        _stale_path, stale_storage_path = build_storage_path(alice_id, stale_file_id, ".md")
        with Session(self.sync_engine) as session:
            session.add(
                File(
                    id=stale_file_id,
                    owner_user_id=alice_id,
                    original_name="old.md",
                    file_type="markdown",
                    storage_path=stale_storage_path,
                    size_bytes=len(content),
                    md5=md5_hash,
                    batch_id=None,
                )
            )
            session.commit()

        response = self.client.post(
            f"/api/library/entries/{bib_id}/markdown",
            headers=self.login_headers("alice"),
            files={"file": ("paper.md", content, "text/markdown")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["markdown_source_file_id"], stale_file_id)

        page = self.client.get("/api/library/entries/page", headers=self.login_headers("alice"))
        self.assertEqual(page.status_code, 200, page.text)

        detail = self.client.get(f"/api/library/entries/{bib_id}", headers=self.login_headers("alice"))
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["markdown_source_file_id"], stale_file_id)

    def test_library_update_allows_editing_metadata_fields(self) -> None:
        alice_id = self.register("alice")
        bib_id, _job_id = self.create_entry_with_timeline(alice_id)

        response = self.client.patch(
            f"/api/library/entries/{bib_id}",
            headers=self.login_headers("alice"),
            json={
                "title": "Updated Title",
                "doi": "10.1000/updated",
                "tags": ["vip", "important"],
                "note": "Updated note",
                "is_pinned": 1,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["title"], "Updated Title")
        self.assertEqual(body["doi"], "10.1000/updated")
        self.assertEqual(body["tags"], ["vip", "important"])
        self.assertEqual(body["note"], "Updated note")
        self.assertEqual(body["is_pinned"], 1)

    def test_library_update_rejects_non_owner(self) -> None:
        alice_id = self.register("alice")
        self.register("bob")
        bib_id, _job_id = self.create_entry_with_timeline(alice_id)

        response = self.client.patch(
            f"/api/library/entries/{bib_id}",
            headers=self.login_headers("bob"),
            json={"title": "Bob edits Alice"},
        )
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()
