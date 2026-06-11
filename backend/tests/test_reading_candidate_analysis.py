from __future__ import annotations

from collections import Counter
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.reading_candidate_analysis import (  # noqa: E402
    CandidateRecord,
    _aggregate_final_summary,
    _cluster_key,
    filter_analysis_cache,
)


def _record(*, title: str, abstract: str = "", keywords: list[str] | None = None, tags: list[str] | None = None) -> CandidateRecord:
    return CandidateRecord(
        entry_id="entry-1",
        title=title,
        journal="",
        year=2024,
        citation_count=10,
        reading_status="none",
        metadata_completeness="full",
        has_fulltext=True,
        keywords=keywords or [],
        tags=tags or [],
        abstract=abstract,
    )


class ReadingCandidateAnalysisTests(unittest.TestCase):
    def test_cluster_key_merges_genai_variants(self) -> None:
        record = _record(
            title="Generative AI adoption in firms",
            keywords=["GenAI", "Artificial Intelligence"],
        )
        self.assertEqual(_cluster_key(record), "生成式人工智能 / GenAI")

    def test_cluster_key_merges_climate_change_case_variants(self) -> None:
        record = _record(
            title="climate change and agricultural resilience",
            abstract="Climate Change creates new environmental risks for crops.",
        )
        self.assertEqual(_cluster_key(record), "气候变化与环境")

    def test_cluster_key_prefers_llm_over_general_ai(self) -> None:
        record = _record(
            title="Large language models and AI adoption in education",
            keywords=["LLM", "Artificial Intelligence"],
        )
        self.assertEqual(_cluster_key(record), "大语言模型 / ChatGPT")

    def test_aggregate_final_summary_includes_long_tail_breakdown(self) -> None:
        summary = _aggregate_final_summary(
            topic="test",
            total_count=100,
            cluster_counter=Counter({
                "生成式人工智能 / GenAI": 30,
                "大语言模型 / ChatGPT": 15,
                "金融与资本市场": 12,
                "营销与消费者行为": 10,
                "运营与供应链": 8,
                "公司治理与战略管理": 7,
                "平台与生态系统": 6,
                "组织行为与人力资源": 5,
                "创业与中小企业": 4,
                "教育与学习": 3,
                "气候变化与环境": 2,
                "农业与作物科学": 1,
                "ESG / 可持续发展": 1,
                "医疗与健康": 1,
            }),
            tier_counter=Counter(),
            ranked_records=[],
        )
        self.assertEqual(summary["clusters"][0]["label"], "生成式人工智能 / GenAI")
        self.assertGreater(summary["long_tail_count"], 0)
        self.assertTrue(any(item["label"] == "ESG / 可持续发展" for item in summary["long_tail_clusters"]))

    def test_filter_analysis_cache_returns_subset_without_rescanning(self) -> None:
        analysis_cache = {
            "cache_id": "cache-root",
            "query": "*",
            "reading_status": "none",
            "entries": [
                {
                    "entry_id": "entry-1",
                    "title": "Paper A",
                    "journal": "Academy of Management Journal",
                    "year": 2024,
                    "citation_count": 20,
                    "reading_status": "none",
                    "metadata_completeness": "full",
                    "has_fulltext": True,
                    "priority_score": 0.92,
                    "cluster_labels": ["生成式人工智能 / GenAI"],
                    "local_rule_reasons": ["命中高质量期刊名录：Management UTD 24 (Selected)"],
                    "journal_quality": {"label": "Management UTD 24 (Selected)", "matched_name": "Academy of Management Journal"},
                },
                {
                    "entry_id": "entry-2",
                    "title": "Paper B",
                    "journal": "Journal of Retailing",
                    "year": 2023,
                    "citation_count": 8,
                    "reading_status": "none",
                    "metadata_completeness": "full",
                    "has_fulltext": False,
                    "priority_score": 0.44,
                    "cluster_labels": ["营销与消费者行为"],
                    "local_rule_reasons": [],
                    "journal_quality": None,
                },
            ],
        }
        result = filter_analysis_cache(
            analysis_cache=analysis_cache,
            topic="专注看 Management UTD 24 的 GenAI 文献",
            journal_tier_labels=["Management UTD 24 (Selected)"],
            cluster_labels=["生成式人工智能 / GenAI"],
            require_fulltext=True,
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["analysis_cache"]["source_scope"], "analysis_cache_subset")
        self.assertEqual(result["analysis_cache"]["parent_cache_id"], "cache-root")
        self.assertEqual(result["analysis_cache"]["reused_from_cache_id"], "cache-root")
        self.assertEqual(result["analysis_cache"]["entries"][0]["entry_id"], "entry-1")
        self.assertIn("未重新全量扫描文献库", result["note"])

    def test_filter_analysis_cache_supports_max_entries_cutoff(self) -> None:
        analysis_cache = {
            "cache_id": "cache-root",
            "query": "*",
            "reading_status": "none",
            "entries": [
                {
                    "entry_id": "entry-1",
                    "title": "Paper A",
                    "journal": "AER",
                    "year": 2024,
                    "citation_count": 20,
                    "reading_status": "none",
                    "metadata_completeness": "full",
                    "has_fulltext": True,
                    "priority_score": 0.92,
                    "cluster_labels": ["生成式人工智能 / GenAI"],
                    "local_rule_reasons": [],
                    "journal_quality": {"label": "Economics Top 5", "matched_name": "American Economic Review"},
                },
                {
                    "entry_id": "entry-2",
                    "title": "Paper B",
                    "journal": "QJE",
                    "year": 2024,
                    "citation_count": 15,
                    "reading_status": "none",
                    "metadata_completeness": "full",
                    "has_fulltext": True,
                    "priority_score": 0.87,
                    "cluster_labels": ["生成式人工智能 / GenAI"],
                    "local_rule_reasons": [],
                    "journal_quality": {"label": "Economics Top 5", "matched_name": "Quarterly Journal of Economics"},
                },
            ],
        }
        result = filter_analysis_cache(
            analysis_cache=analysis_cache,
            topic="只看 economics top 5",
            journal_tier_labels=["Economics Top 5"],
            max_entries=1,
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(len(result["analysis_cache"]["entries"]), 1)
        self.assertEqual(result["analysis_cache"]["entries"][0]["entry_id"], "entry-1")


if __name__ == "__main__":
    unittest.main()
