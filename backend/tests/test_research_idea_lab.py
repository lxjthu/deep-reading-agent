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


if __name__ == "__main__":
    unittest.main()
