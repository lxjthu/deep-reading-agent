from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers import reading  # noqa: E402


class TestReadingConcurrencyConfig(unittest.TestCase):
    def test_parse_positive_int_uses_default_for_invalid_values(self):
        self.assertEqual(reading._parse_positive_int("abc", 3), 3)
        self.assertEqual(reading._parse_positive_int("0", 3), 3)
        self.assertEqual(reading._parse_positive_int("-2", 3), 3)
        self.assertEqual(reading._parse_positive_int(None, 3), 3)

    def test_parse_positive_int_accepts_positive_values(self):
        self.assertEqual(reading._parse_positive_int("5", 3), 5)

    def test_default_concurrency_is_conservative(self):
        self.assertEqual(reading.READING_FILE_CONCURRENCY, 3)
        self.assertEqual(reading.LONG_DIMENSION_CONCURRENCY, 6)

    def test_default_quant_and_qual_concurrency_are_conservative(self):
        self.assertEqual(reading.QUANT_STEP_CONCURRENCY, 4)
        self.assertEqual(reading.QUAL_STEP_CONCURRENCY, 3)
