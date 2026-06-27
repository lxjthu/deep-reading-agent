from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.research_idea_lab import extract_constructs_from_evidence  # noqa: E402


class ResearchIdeaLabTests(unittest.TestCase):
    def test_extract_constructs_uses_evidence_terms_and_preserves_sources(self) -> None:
        evidence_pack = {
            "entries": [
                {
                    "entry_id": "entry-1",
                    "title": "Digital Capability and Firm Resilience",
                    "evidence": [
                        {
                            "source_tier": "P0",
                            "source_kind": "abstract",
                            "text": "Digital capability improves firm resilience through innovation efficiency.",
                        },
                        {
                            "source_tier": "P1",
                            "source_kind": "user_note",
                            "text": "Potential mediator: innovation efficiency. Risk: reverse causality.",
                        },
                    ],
                }
            ]
        }

        result = extract_constructs_from_evidence(
            evidence_pack=evidence_pack,
            topic="digital capability and firm resilience",
            max_constructs=5,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["topic"], "digital capability and firm resilience")
        self.assertGreaterEqual(len(result["constructs"]), 1)
        first = result["constructs"][0]
        self.assertIn("name", first)
        self.assertIn("evidence", first)
        self.assertEqual(first["evidence"][0]["entry_id"], "entry-1")
        self.assertEqual(first["evidence"][0]["source_tier"], "P0")
        self.assertIn("limitations", result)

    def test_diagnose_research_gaps_flags_missing_identification(self) -> None:
        from services.research_idea_lab import diagnose_research_gaps

        construct_result = {
            "constructs": [
                {
                    "construct_id": "construct_1",
                    "name": "digital capability",
                    "definition": "Digital capability may improve firm resilience.",
                    "mechanisms": ["through"],
                    "empirical_design": {"data_sources": [], "identification": [], "risks": []},
                    "evidence": [
                        {
                            "entry_id": "entry-1",
                            "source_tier": "P0",
                            "quote": "Digital capability improves resilience.",
                        }
                    ],
                }
            ]
        }

        result = diagnose_research_gaps(construct_result=construct_result, topic="digital capability")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["gaps"][0]["gap_type"], "causal_identification")
        self.assertIn("identification", result["gaps"][0]["needed_evidence"][0].lower())

    def test_generate_research_ideas_uses_constructs_and_gaps(self) -> None:
        from services.research_idea_lab import generate_research_ideas

        construct_result = {
            "topic": "digital capability",
            "constructs": [
                {
                    "construct_id": "construct_1",
                    "name": "digital capability",
                    "definition": "Digital capability improves resilience through innovation efficiency.",
                    "mechanisms": ["through"],
                    "evidence": [
                        {
                            "entry_id": "entry-1",
                            "source_tier": "P0",
                            "quote": "Digital capability improves resilience.",
                        }
                    ],
                }
            ],
        }
        gap_result = {
            "gaps": [
                {
                    "gap_id": "gap_1",
                    "gap_type": "mechanism",
                    "summary": "The mediating mechanism is under-specified.",
                    "confidence": "medium",
                }
            ]
        }

        result = generate_research_ideas(
            construct_result=construct_result,
            gap_result=gap_result,
            max_ideas=3,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["ideas"]), 1)
        idea = result["ideas"][0]
        self.assertIn("research_question", idea)
        self.assertIn("hypotheses", idea)
        self.assertEqual(idea["evidence_refs"], ["entry-1"])

if __name__ == "__main__":
    unittest.main()

