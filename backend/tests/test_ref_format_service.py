from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.ref_format_service import (  # noqa: E402
    BibEntryForFormat,
    generate_formatted_references,
    serialize_bib_entry,
)


class RefFormatServiceTests(unittest.TestCase):
    def test_serialize_bib_entry_preserves_metadata(self):
        entry = BibEntryForFormat(
            id="bib-1",
            title="数字化转型与企业韧性",
            authors=["张三", "李四"],
            year=2024,
            journal="经济研究",
            volume="59",
            issue="2",
            pages="12-31",
            doi="10.1234/example",
            language="zh",
        )

        payload = serialize_bib_entry(entry, order=3)

        self.assertEqual(payload["order"], 3)
        self.assertEqual(payload["id"], "bib-1")
        self.assertEqual(payload["title"], "数字化转型与企业韧性")
        self.assertEqual(payload["authors"], ["张三", "李四"])
        self.assertEqual(payload["year"], 2024)
        self.assertEqual(payload["journal"], "经济研究")
        self.assertEqual(payload["volume"], "59")
        self.assertEqual(payload["issue"], "2")
        self.assertEqual(payload["pages"], "12-31")
        self.assertEqual(payload["doi"], "10.1234/example")
        self.assertEqual(payload["language"], "zh")

    def test_generate_formatted_references_batches_and_renumbers(self):
        entries = [
            BibEntryForFormat(
                id=f"bib-{idx}",
                title=f"Title {idx}",
                authors=[f"Author {idx}"],
                year=2020 + idx,
            )
            for idx in range(1, 33)
        ]

        def fake_call(messages, **kwargs):
            user_text = messages[-1]["content"]
            if '"order": 1' in user_text:
                return {"references": [{"order": i, "formatted": f"old-{i}"} for i in range(1, 31)]}
            return {"references": [{"order": 31, "formatted": "old-31"}, {"order": 32, "formatted": "old-32"}]}

        with patch("services.ref_format_service.call_deepseek_json", side_effect=fake_call) as mocked:
            result = generate_formatted_references(
                entries,
                format_rules="每条以编号开头。",
                format_name="测试格式",
                api_key="sk-test",
                batch_size=30,
            )

        self.assertEqual(mocked.call_count, 2)
        lines = result.splitlines()
        self.assertEqual(len(lines), 32)
        self.assertEqual(lines[0], "[1] old-1")
        self.assertEqual(lines[30], "[31] old-31")
        self.assertEqual(lines[31], "[32] old-32")


if __name__ == "__main__":
    unittest.main()
