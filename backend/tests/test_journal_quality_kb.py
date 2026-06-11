from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.journal_quality_kb import (  # noqa: E402
    build_journal_quality_matcher,
    lookup_journal_tier,
    lookup_journal_tier_with_matcher,
    score_journal_quality,
    score_journal_quality_with_matcher,
)


class JournalQualityKbTests(unittest.TestCase):
    def test_lookup_journal_tier_matches_english_alias(self) -> None:
        match = lookup_journal_tier("Academy of Management Journal")
        self.assertIsNotNone(match)
        self.assertEqual(match.label, "Management UTD 24 (Selected)")

    def test_lookup_journal_tier_matches_chinese_name(self) -> None:
        match = lookup_journal_tier("《管理世界》")
        self.assertIsNotNone(match)
        self.assertEqual(match.label, "Chinese Top Tier")

    def test_lookup_journal_tier_does_not_confuse_short_abbreviation_with_research_titles(self) -> None:
        matcher = build_journal_quality_matcher(
            "- **Economics Top 5**: American Economic Review, AER, Quarterly Journal of Economics, QJE, "
            "Journal of Political Economy, JPE, Review of Economic Studies, RES, Econometrica\n"
        )
        self.assertIsNone(lookup_journal_tier_with_matcher(matcher, "Research Policy"))
        self.assertIsNone(lookup_journal_tier_with_matcher(matcher, "Energy Research & Social Science"))
        self.assertIsNone(lookup_journal_tier_with_matcher(matcher, "Operations Research"))

    def test_lookup_journal_tier_keeps_exact_abbreviation_match(self) -> None:
        matcher = build_journal_quality_matcher(
            "- **Economics Top 5**: American Economic Review, AER, Review of Economic Studies, RES\n"
        )
        match = lookup_journal_tier_with_matcher(matcher, "RES")
        self.assertIsNotNone(match)
        self.assertEqual(match.label, "Economics Top 5")
        self.assertEqual(match.matched_name, "RES")

    def test_score_journal_quality_returns_zero_for_unknown_journal(self) -> None:
        score, detail = score_journal_quality("Unknown Journal of Widgets")
        self.assertEqual(score, 0.0)
        self.assertIsNone(detail)

    def test_custom_prompt_content_can_override_journal_registry(self) -> None:
        matcher = build_journal_quality_matcher(
            "- **Custom Tier**: Journal of Widget Economics, JWE\n"
            "- **Economics Top 5**: American Economic Review, AER\n"
        )
        match = lookup_journal_tier_with_matcher(matcher, "Journal of Widget Economics")
        self.assertIsNotNone(match)
        self.assertEqual(match.label, "Custom Tier")

        score, detail = score_journal_quality_with_matcher(matcher, "Journal of Widget Economics")
        self.assertGreater(score, 0.0)
        self.assertEqual(detail["label"], "Custom Tier")


if __name__ == "__main__":
    unittest.main()
