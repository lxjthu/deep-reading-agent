from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEMP_DIR = tempfile.mkdtemp(prefix="dra-research-retrieval-tests-")
TEST_DB_PATH = Path(TEMP_DIR) / "test_research_retrieval.sqlite"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("DEPLOY_SECRET", "test-deploy-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("JWT_ALGORITHM", "HS256")

from db import AsyncSessionLocal, Base, SYNC_DATABASE_URL, engine as async_engine  # noqa: E402
from db.models import (  # noqa: E402
    Annotation,
    BibEntry,
    BibReference,
    BibReferenceCitation,
    CardNote,
    File,
    Job,
    ReadingItem,
    ReadingItemEdit,
    ReadingSourceEvidence,
    User,
)
from services.research_retrieval import ResearchQuery, get_evidence_pack, research_search  # noqa: E402


class ResearchRetrievalTests(unittest.TestCase):
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

    def seed_library(self) -> dict[str, str]:
        owner_id = 1
        other_owner_id = 2
        entry_id = "entry-platform"
        other_entry_id = "entry-other-user"
        job_id = "job-platform"
        reading_item_id = 101
        reference_id = "ref-platform"

        from sqlalchemy.orm import Session

        with Session(self.sync_engine) as session:
            session.add_all(
                [
                    User(id=owner_id, username="owner", password_hash="x", role="vip"),
                    User(id=other_owner_id, username="other", password_hash="x", role="vip"),
                    File(
                        id="file-md",
                        owner_user_id=owner_id,
                        original_name="platform.md",
                        file_type="markdown",
                        storage_path="uploads/platform.md",
                        size_bytes=100,
                        md5="md5-owner",
                    ),
                    BibEntry(
                        id=entry_id,
                        owner_user_id=owner_id,
                        title="Platform Responsibility in Digital Governance",
                        authors_json=json.dumps(["Alice"]),
                        year=2024,
                        doi="10.1000/platform",
                        journal="Governance Studies",
                        abstract="The original abstract says platform responsibility is central to digital governance.",
                        abstract_cn=None,
                        keywords_json=json.dumps(["platform responsibility", "digital governance"]),
                        source_db="manual",
                        source_file_id="file-md",
                        markdown_source_file_id="file-md",
                        user_tags_json=json.dumps(["governance"]),
                        user_note="Human note: accountability mechanisms matter for platform responsibility.",
                        reading_status="read",
                        metadata_completeness="partial",
                        dedup_key="platform-responsibility",
                    ),
                    BibEntry(
                        id=other_entry_id,
                        owner_user_id=other_owner_id,
                        title="Other User Platform Responsibility",
                        authors_json=json.dumps(["Eve"]),
                        year=2024,
                        source_db="manual",
                        keywords_json="[]",
                        user_tags_json="[]",
                        abstract="Other user's private platform responsibility abstract.",
                        reading_status="none",
                        metadata_completeness="partial",
                        dedup_key="other-platform-responsibility",
                    ),
                    Job(
                        id=job_id,
                        owner_user_id=owner_id,
                        job_type="reading_long",
                        status="success",
                        input_file_id="file-md",
                    ),
                    ReadingItem(
                        id=reading_item_id,
                        owner_user_id=owner_id,
                        bib_entry_id=entry_id,
                        job_id=job_id,
                        mode="long",
                        section_type="dimension",
                        item_key="theory",
                        item_label="Theory",
                        sort_order=1,
                        content="AI note: platform responsibility is only a minor implication.",
                    ),
                    ReadingItemEdit(
                        reading_item_id=reading_item_id,
                        owner_user_id=owner_id,
                        edited_content="Edited human reading: platform responsibility is the core argument.",
                    ),
                    ReadingSourceEvidence(
                        owner_user_id=owner_id,
                        bib_entry_id=entry_id,
                        job_id=job_id,
                        reading_item_id=reading_item_id,
                        source_file_id="file-md",
                        source_version="original",
                        source_tier="P0",
                        validation_status="exact",
                        mode="long",
                        item_key="theory",
                        item_label="Theory",
                        evidence_role="finding",
                        claim_text="The paper treats platform responsibility as a core obligation.",
                        quote_text="Original source text states that platform responsibility must be treated as a core governance obligation.",
                        quote_hash="source-evidence-platform",
                        section_hint="Findings",
                        char_start=10,
                        char_end=110,
                        match_score=1.0,
                        metadata_json="{}",
                    ),
                    Annotation(
                        id="anno-human",
                        owner_user_id=owner_id,
                        source_type="library_note",
                        source_id=entry_id,
                        bib_entry_id=entry_id,
                        selected_text="platform responsibility",
                        note="Annotation says responsibility should be compared with accountability.",
                        is_ai_generated=0,
                    ),
                    Annotation(
                        id="anno-ai",
                        owner_user_id=owner_id,
                        source_type="ai_summary",
                        source_id=entry_id,
                        bib_entry_id=entry_id,
                        note="AI annotation mentions platform responsibility as a summary label.",
                        is_ai_generated=1,
                    ),
                    CardNote(
                        id="card-platform",
                        owner_user_id=owner_id,
                        source_bib_entry_id=entry_id,
                        source_version="original",
                        title="Platform responsibility card",
                        summary="Card summary about platform responsibility.",
                        tags_json=json.dumps(["accountability"]),
                        selected_text="responsibility passage",
                        body_markdown="Card body links platform responsibility to public governance.",
                    ),
                    BibReference(
                        id=reference_id,
                        owner_user_id=owner_id,
                        source_bib_entry_id=entry_id,
                        raw_text="Reference raw text about platform responsibility.",
                        title="Referenced Platform Responsibility Study",
                    ),
                    BibReferenceCitation(
                        id="citation-platform",
                        owner_user_id=owner_id,
                        source_bib_entry_id=entry_id,
                        bib_reference_id=reference_id,
                        quote_text="The cited passage explicitly discusses platform responsibility.",
                        excerpt="Original citation excerpt with platform responsibility.",
                    ),
                ]
            )
            session.commit()
        return {"owner_id": owner_id, "entry_id": entry_id}

    def test_research_search_ranks_source_tiers_and_keeps_user_data_isolated(self) -> None:
        ids = self.seed_library()

        async def run():
            async with AsyncSessionLocal() as session:
                return await research_search(
                    session,
                    owner_user_id=ids["owner_id"],
                    query=ResearchQuery(
                        question="platform responsibility",
                        limit_entries=10,
                        limit_evidence_per_entry=20,
                    ),
                )

        result = asyncio.run(run())
        entry_ids = [entry["entry_id"] for entry in result["entries"]]
        self.assertEqual(entry_ids, [ids["entry_id"]])
        evidence = result["entries"][0]["evidence"]
        tiers = [item["source_tier"] for item in evidence]
        first_p1 = tiers.index("P1")
        last_p0 = max(index for index, tier in enumerate(tiers) if tier == "P0")
        self.assertLess(last_p0, first_p1)
        self.assertLess(
            min(item["score"] for item in evidence if item["source_tier"] == "P0"),
            max(item["score"] for item in evidence if item["source_tier"] == "P0") + 1,
        )
        self.assertTrue(any(item["source_kind"] == "edited_reading_item" for item in evidence))
        self.assertTrue(any(item["source_kind"] == "source_evidence" and item["source_tier"] == "P0" for item in evidence))
        self.assertTrue(any(item["source_kind"] == "reading_item" and item["source_tier"] == "P2" for item in evidence))

    def test_get_evidence_pack_prefers_edited_notes_over_ai_reading_items(self) -> None:
        ids = self.seed_library()

        async def run():
            async with AsyncSessionLocal() as session:
                return await get_evidence_pack(
                    session,
                    owner_user_id=ids["owner_id"],
                    query=ResearchQuery(
                        question="platform responsibility",
                        entry_ids=[ids["entry_id"]],
                        limit_evidence_per_entry=20,
                    ),
                )

        pack = asyncio.run(run())
        evidence = pack["entries"][0]["evidence"]
        source_index = next(i for i, item in enumerate(evidence) if item["source_kind"] == "source_evidence")
        edited_index = next(i for i, item in enumerate(evidence) if item["source_kind"] == "edited_reading_item")
        ai_index = next(i for i, item in enumerate(evidence) if item["source_kind"] == "reading_item")
        self.assertLess(source_index, edited_index)
        self.assertLess(edited_index, ai_index)
        self.assertIn("未联网", "".join(pack["limitations"]))


if __name__ == "__main__":
    unittest.main()
