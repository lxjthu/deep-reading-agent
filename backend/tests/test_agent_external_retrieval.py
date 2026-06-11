from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.agent_external_retrieval import build_cnki_title_search_url  # noqa: E402


class AgentExternalRetrievalTests(unittest.TestCase):
    def test_build_cnki_title_search_url_uses_title_field_query(self) -> None:
        url = build_cnki_title_search_url("数字治理 平台责任")
        self.assertTrue(url.startswith("https://kns.cnki.net/kns8s/defaultresult/index?"))
        self.assertIn("korder=TI", url)
        self.assertIn("%E6%95%B0%E5%AD%97%E6%B2%BB%E7%90%86", url)


if __name__ == "__main__":
    unittest.main()
