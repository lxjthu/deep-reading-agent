from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.reading_source_evidence import (  # noqa: E402
    SOURCE_EVIDENCE_BLOCK_END,
    SOURCE_EVIDENCE_BLOCK_START,
    split_answer_and_evidence,
    validate_source_evidence_candidates,
)


class ReadingSourceEvidenceTests(unittest.TestCase):
    def test_split_answer_and_evidence_extracts_hidden_json(self) -> None:
        raw = (
            "## 识别策略\n\n"
            "作者使用双重差分方法。\n\n"
            f"{SOURCE_EVIDENCE_BLOCK_START}\n"
            "{\"items\":[{\"claim\":\"DID method\",\"quote\":\"We use a difference-in-differences design.\",\"evidence_role\":\"method\"}]}\n"
            f"{SOURCE_EVIDENCE_BLOCK_END}"
        )

        answer, candidates, parse_error = split_answer_and_evidence(raw)

        self.assertIsNone(parse_error)
        self.assertEqual(answer.strip(), "## 识别策略\n\n作者使用双重差分方法。")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["quote"], "We use a difference-in-differences design.")

    def test_split_answer_and_evidence_returns_raw_answer_on_bad_json(self) -> None:
        raw = (
            "正文\n"
            f"{SOURCE_EVIDENCE_BLOCK_START}\n"
            "{bad json\n"
            f"{SOURCE_EVIDENCE_BLOCK_END}"
        )

        answer, candidates, parse_error = split_answer_and_evidence(raw)

        self.assertEqual(answer.strip(), "正文")
        self.assertEqual(candidates, [])
        self.assertIsNotNone(parse_error)

    def test_validate_source_evidence_candidates_marks_exact_match_as_p0(self) -> None:
        paper_text = "Introduction\nWe use a difference-in-differences design to estimate policy effects.\nConclusion"
        candidates = [
            {
                "claim": "作者使用DID识别政策影响",
                "quote": "We use a difference-in-differences design to estimate policy effects.",
                "evidence_role": "method",
                "section_hint": "Introduction",
            }
        ]

        records = validate_source_evidence_candidates(
            candidates,
            paper_text=paper_text,
            max_records=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["validation_status"], "exact")
        self.assertEqual(records[0]["source_tier"], "P0")
        self.assertEqual(records[0]["char_start"], len("Introduction\n"))
        self.assertGreater(records[0]["char_end"], records[0]["char_start"])

    def test_validate_source_evidence_candidates_does_not_promote_unmatched_quote(self) -> None:
        paper_text = "The actual paper text does not contain the generated sentence."
        candidates = [
            {
                "claim": "模型声称存在某个结论",
                "quote": "This exact quote is not in the paper.",
                "evidence_role": "finding",
            }
        ]

        records = validate_source_evidence_candidates(
            candidates,
            paper_text=paper_text,
            max_records=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["validation_status"], "unmatched")
        self.assertEqual(records[0]["source_tier"], "P2")


if __name__ == "__main__":
    unittest.main()
