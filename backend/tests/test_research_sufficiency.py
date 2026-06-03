from __future__ import annotations

import unittest

from backend.services.research_sufficiency import assess_evidence_sufficiency
from backend.services.research_agent_runtime import update_state_after_tool


class ResearchSufficiencyTest(unittest.TestCase):
    def test_p0_or_p1_evidence_is_sufficient(self) -> None:
        pack = {
            "entries": [
                {
                    "entry_id": "e1",
                    "evidence": [
                        {"source_tier": "P2", "quote": "AI note"},
                        {"source_tier": "P0", "quote": "Original abstract"},
                    ],
                },
                {
                    "entry_id": "e2",
                    "evidence": [{"source_tier": "P1", "quote": "User note"}],
                },
            ]
        }

        result = assess_evidence_sufficiency(pack, user_requested_external=False)

        self.assertEqual(result["status"], "sufficient")
        self.assertTrue(result["can_answer"])
        self.assertFalse(result["needs_external_consent"])
        self.assertEqual(result["tier_summary"], {"P0": 1, "P1": 1, "P2": 1, "P3": 0})

    def test_p2_only_evidence_warns_but_can_answer(self) -> None:
        pack = {
            "entries": [
                {
                    "entry_id": "e1",
                    "evidence": [
                        {"source_tier": "P2", "quote": "AI generated reading note"},
                    ],
                }
            ]
        }

        result = assess_evidence_sufficiency(pack, user_requested_external=False)

        self.assertEqual(result["status"], "p2_only")
        self.assertTrue(result["can_answer"])
        self.assertFalse(result["needs_external_consent"])
        self.assertIn("AI", result["message"])

    def test_external_request_with_weak_evidence_requires_consent(self) -> None:
        pack = {"entries": [{"entry_id": "e1", "evidence": [{"source_tier": "P2"}]}]}

        result = assess_evidence_sufficiency(pack, user_requested_external=True)

        self.assertEqual(result["status"], "needs_external_consent")
        self.assertFalse(result["can_answer"])
        self.assertTrue(result["needs_external_consent"])

    def test_empty_evidence_is_insufficient(self) -> None:
        result = assess_evidence_sufficiency({"entries": []}, user_requested_external=False)

        self.assertEqual(result["status"], "insufficient")
        self.assertFalse(result["can_answer"])
        self.assertFalse(result["needs_external_consent"])
        self.assertEqual(result["evidence_count"], 0)

    def test_get_evidence_pack_updates_runtime_sufficiency_state(self) -> None:
        state = update_state_after_tool(
            {},
            name="get_evidence_pack",
            args={"question": "What does the paper say?"},
            result={
                "entries": [
                    {
                        "entry_id": "e1",
                        "title": "Paper",
                        "evidence": [{"source_tier": "P0", "quote": "Original evidence"}],
                    }
                ]
            },
        )

        self.assertEqual(state["last_sufficiency"]["status"], "sufficient")
        self.assertEqual(state["last_sufficiency"]["tier_summary"]["P0"], 1)


if __name__ == "__main__":
    unittest.main()
