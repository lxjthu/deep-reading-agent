from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db.models import UploadBatch  # noqa: E402
from routers.agent import _build_scan_plan, _summarize_scan_result, _summarize_upload_results  # noqa: E402
from services.research_agent_runtime import summarize_state_for_ui  # noqa: E402


class AgentInboxObservabilityTests(unittest.TestCase):
    def test_summarize_upload_results_tracks_counts_examples_and_recommendations(self) -> None:
        batch = UploadBatch(
            id="batch-1",
            owner_user_id=1,
            source_type="folder",
            total_files=4,
            succeeded=3,
            failed=1,
            status="partial",
            note="agent_inbox",
            created_at=datetime(2026, 5, 28, 10, 30, 0),
        )
        summary = _summarize_upload_results(
            batch,
            [
                {
                    "success": True,
                    "deduplicated": False,
                    "file_id": "file-1",
                    "filename": "paper-a.pdf",
                    "matched_bib_entry_id": "entry-1",
                },
                {
                    "success": True,
                    "deduplicated": True,
                    "file_id": "file-2",
                    "filename": "paper-b.pdf",
                    "matched_bib_entry_id": None,
                },
                {
                    "success": True,
                    "deduplicated": False,
                    "file_id": "file-3",
                    "filename": "paper-c.md",
                    "matched_bib_entry_id": None,
                },
                {
                    "success": False,
                    "filename": "paper-d.docx",
                    "error": "unsupported_extension",
                },
            ],
        )
        self.assertEqual(summary["imported_count"], 2)
        self.assertEqual(summary["deduplicated_count"], 1)
        self.assertEqual(summary["matched_count"], 1)
        self.assertEqual(summary["unmatched_count"], 2)
        self.assertEqual(summary["error_counts"]["unsupported_extension"], 1)
        self.assertEqual(summary["failed_examples"][0]["message"], "文件扩展名不受支持")
        self.assertTrue(any("处理失败文件" in item for item in summary["recommendations"]))
        self.assertTrue(any("重复文件" in item for item in summary["recommendations"]))

    def test_summarize_scan_result_tracks_library_distribution_and_skipped_examples(self) -> None:
        summary = _summarize_scan_result(
            source="upload_batch",
            topic="企业人工智能",
            scanned=4,
            rows=[
                {
                    "title": "Paper A",
                    "relevant": True,
                    "library_match": {"status": "in_library"},
                },
                {
                    "title": "Paper B",
                    "relevant": True,
                    "library_match": {"status": "possible_match"},
                },
                {
                    "title": "Paper C",
                    "relevant": False,
                    "library_match": {"status": "not_in_library"},
                },
                {
                    "title": "Paper D",
                    "relevant": False,
                    "library_match": {"status": "file_exists_no_bib_entry"},
                },
            ],
            skipped=[
                {"filename": "bad.docx", "reason": "unsupported_for_reading"},
                {"filename": "empty.pdf", "reason": "empty_file"},
            ],
            input_batch_id="batch-1",
        )
        self.assertEqual(summary["candidate_count"], 4)
        self.assertEqual(summary["relevant_count"], 2)
        self.assertEqual(summary["library_counts"]["in_library"], 1)
        self.assertEqual(summary["library_counts"]["possible_match"], 1)
        self.assertEqual(summary["library_counts"]["not_in_library"], 1)
        self.assertEqual(summary["library_counts"]["file_exists_no_bib_entry"], 1)
        self.assertEqual(summary["skipped_reasons"]["unsupported_for_reading"], 1)
        self.assertEqual(summary["skipped_examples"][1]["message"], "空文件")
        self.assertTrue(any("人工确认" in item for item in summary["recommendations"]))
        self.assertTrue(any("跳过" in item for item in summary["recommendations"]))

    def test_scan_summary_tracks_next_batch_workflow(self) -> None:
        scan_plan = _build_scan_plan(total_available=200, offset=0, batch_size=100, scanned=100)
        summary = _summarize_scan_result(
            source="upload_batch",
            topic="*",
            scanned=100,
            rows=[
                {"title": f"Paper {index}", "relevant": True, "library_match": {"status": "in_library"}}
                for index in range(100)
            ],
            skipped=[],
            input_batch_id="batch-1",
            scan_plan=scan_plan,
        )
        self.assertTrue(summary["scan_plan"]["has_next_batch"])
        self.assertEqual(summary["scan_plan"]["next_offset"], 100)
        self.assertEqual(summary["scan_plan"]["remaining_count"], 100)
        self.assertIn("scan_input_folder", summary["scan_plan"]["next_tool"])
        self.assertTrue(any("scan_input_folder" in item for item in summary["recommendations"]))

    def test_ui_summary_includes_last_scan_summary(self) -> None:
        ui_state = summarize_state_for_ui(
            {
                "last_scan": {
                    "summary": {
                        "source": "upload_batch",
                        "topic": "企业人工智能",
                        "batch_id": "batch-1",
                        "scanned": 10,
                        "candidate_count": 6,
                        "relevant_count": 3,
                        "library_counts": {"in_library": 2},
                        "skipped_count": 1,
                        "skipped_reasons": {"unsupported_for_reading": 1},
                        "scan_plan": {
                            "batch_size": 100,
                            "offset": 0,
                            "next_offset": 100,
                            "processed_total": 100,
                            "total_available": 200,
                            "remaining_count": 100,
                            "has_next_batch": True,
                            "next_tool": "scan_input_folder",
                            "workflow_steps": ["settle_notes", "scan_next_batch", "iterate_notes", "final_result"],
                        },
                        "skipped_examples": [{"filename": "bad.docx", "message": "文件类型不支持扫描"}],
                        "recommendations": ["先处理失败文件。"],
                    }
                }
            }
        )
        self.assertEqual(ui_state["last_scan_summary"]["topic"], "企业人工智能")
        self.assertEqual(ui_state["last_scan_summary"]["batch_id"], "batch-1")
        self.assertEqual(ui_state["last_scan_summary"]["library_counts"]["in_library"], 2)
        self.assertEqual(ui_state["last_scan_summary"]["skipped_examples"][0]["filename"], "bad.docx")
        self.assertTrue(ui_state["last_scan_summary"]["scan_plan"]["has_next_batch"])


if __name__ == "__main__":
    unittest.main()
