from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi import HTTPException


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers.agent import classify_agent_exception  # noqa: E402


class RateLimitError(Exception):
    status_code = 429


class AgentErrorTaxonomyTests(unittest.TestCase):
    def test_invalid_api_key_value_error_is_classified(self) -> None:
        payload = classify_agent_exception(
            ValueError("API Key 长度不足，可能不完整。请重新复制完整的 Key。"),
            stage="input_validation",
            provider="deepseek",
        )
        self.assertEqual(payload["code"], "invalid_api_key")
        self.assertFalse(payload["retryable"])
        self.assertEqual(payload["stage"], "input_validation")

    def test_http_not_found_is_classified(self) -> None:
        payload = classify_agent_exception(
            HTTPException(status_code=404, detail="Agent session not found"),
            stage="session_lookup",
        )
        self.assertEqual(payload["code"], "resource_not_found")
        self.assertEqual(payload["status_code"], 404)

    def test_rate_limit_error_is_retryable(self) -> None:
        payload = classify_agent_exception(
            RateLimitError("Too many requests"),
            stage="llm_completion",
            provider="deepseek",
        )
        self.assertEqual(payload["code"], "llm_rate_limited")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["provider"], "deepseek")

    def test_generic_tool_error_is_classified_with_tool_name(self) -> None:
        payload = classify_agent_exception(
            RuntimeError("boom"),
            stage="tool_execution",
            tool="get_evidence_pack",
        )
        self.assertEqual(payload["code"], "tool_execution_error")
        self.assertEqual(payload["tool"], "get_evidence_pack")


if __name__ == "__main__":
    unittest.main()
