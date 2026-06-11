from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.llm_provider import describe_llm_provider, probe_llm_provider  # noqa: E402


class _FakeResponseMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeResponseMessage(content)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = type("ChatNamespace", (), {})()
        self.chat.completions = type("CompletionNamespace", (), {})()
        self.chat.completions.create = lambda **kwargs: _FakeResponse(content)


class LLMProviderTests(unittest.TestCase):
    def test_describe_llm_provider_defaults_to_deepseek(self) -> None:
        info = describe_llm_provider("sk-abcdefghijklmnopqrstuvwxyz", requested_model="deepseek-v4-flash")
        self.assertEqual(info["provider"], "deepseek")
        self.assertEqual(info["provider_label"], "DeepSeek")
        self.assertEqual(info["model"], "deepseek-v4-flash")

    def test_describe_llm_provider_detects_mimo_token_plan(self) -> None:
        info = describe_llm_provider("mimo-token:tp-abcdefghijklmnopqrstuvwxyz", requested_model="deepseek-v4-flash")
        self.assertEqual(info["provider"], "mimo-token-plan")
        self.assertEqual(info["provider_label"], "小米 MiMo Token Plan")
        self.assertEqual(info["model"], "mimo-v2.5-pro")

    @patch("utils.llm_provider.create_openai_client", return_value=_FakeClient("pong"))
    def test_probe_llm_provider_returns_preview_and_latency(self, _mock_client) -> None:
        result = probe_llm_provider("deepseek:sk-abcdefghijklmnopqrstuvwxyz", requested_model="deepseek-v4-flash")
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "deepseek")
        self.assertEqual(result["response_preview"], "pong")
        self.assertIsInstance(result["latency_ms"], int)


if __name__ == "__main__":
    unittest.main()
