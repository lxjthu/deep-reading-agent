from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from openai import OpenAI


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MIMO_PAYG_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_TOKEN_PLAN_CN_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5-pro"

_PLACEHOLDER_KEYS = {
    "sk-xxx",
    "sk-xxxx",
    "sk-your-key",
    "tp-xxx",
    "tp-xxxx",
    "tp-your-key",
    "your-api-key",
}

_MIMO_PAYG_PREFIXES = ("mimo:", "mimo-payg:", "xiaomi:", "xiaomi-payg:")
_MIMO_TOKEN_PREFIXES = ("mimo-token:", "mimo-token-plan:", "xiaomi-token:", "xiaomi-token-plan:")
_DEEPSEEK_PREFIXES = ("deepseek:",)


@dataclass(frozen=True)
class LLMProvider:
    provider: str
    api_key: str
    base_url: str

    def model_for(self, requested_model: str) -> str:
        if self.provider.startswith("mimo-"):
            return MIMO_MODEL
        return requested_model

    def display_name(self) -> str:
        if self.provider == "mimo-payg":
            return "小米 MiMo 按量付费"
        if self.provider == "mimo-token-plan":
            return "小米 MiMo Token Plan"
        return "DeepSeek"


def _strip_provider_prefix(key: str) -> tuple[str | None, str]:
    lowered = key.lower()
    for prefix in _MIMO_PAYG_PREFIXES:
        if lowered.startswith(prefix):
            return "mimo-payg", key[len(prefix):].strip()
    for prefix in _MIMO_TOKEN_PREFIXES:
        if lowered.startswith(prefix):
            return "mimo-token-plan", key[len(prefix):].strip()
    for prefix in _DEEPSEEK_PREFIXES:
        if lowered.startswith(prefix):
            return "deepseek", key[len(prefix):].strip()
    return None, key


def resolve_llm_provider(api_key: Optional[str], *, source: str = "前端设置") -> LLMProvider:
    key = validate_llm_key(api_key, source=source)
    explicit_provider, clean_key = _strip_provider_prefix(key)

    if explicit_provider == "mimo-payg":
        return LLMProvider("mimo-payg", clean_key, MIMO_PAYG_BASE_URL)
    if explicit_provider == "mimo-token-plan":
        return LLMProvider("mimo-token-plan", clean_key, MIMO_TOKEN_PLAN_CN_BASE_URL)
    if explicit_provider == "deepseek":
        return LLMProvider("deepseek", clean_key, os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL))

    if clean_key.startswith("tp-"):
        return LLMProvider("mimo-token-plan", clean_key, MIMO_TOKEN_PLAN_CN_BASE_URL)

    return LLMProvider("deepseek", clean_key, os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL))


def validate_llm_key(api_key: Optional[str], *, source: str = "前端设置") -> str:
    if not api_key or not api_key.strip():
        raise ValueError(f"未提供 API Key。请在{source}中输入你的 Key。")

    key = api_key.strip()
    explicit_provider, clean_key = _strip_provider_prefix(key)

    if clean_key in _PLACEHOLDER_KEYS:
        raise ValueError(f"API Key 为占位符，不能使用。请在{source}中更新为真实 Key。")

    if explicit_provider == "mimo-payg" and not clean_key.startswith("sk-"):
        raise ValueError("小米按量付费 API Key 格式错误，应为 sk- 开头。")
    if explicit_provider == "mimo-token-plan" and not clean_key.startswith("tp-"):
        raise ValueError("小米 Token Plan API Key 格式错误，应为 tp- 开头。")
    if explicit_provider == "deepseek" and not clean_key.startswith("sk-"):
        raise ValueError("DeepSeek API Key 格式错误，应为 sk- 开头。")
    if not explicit_provider and not (clean_key.startswith("sk-") or clean_key.startswith("tp-")):
        raise ValueError("API Key 格式错误，应为 sk- 或 tp- 开头。")

    if len(clean_key) < 20:
        raise ValueError("API Key 长度不足，可能不完整。请重新复制完整的 Key。")

    return key


def create_openai_client(
    api_key: str,
    *,
    timeout: float | httpx.Timeout | None = None,
) -> OpenAI:
    provider = resolve_llm_provider(api_key)
    kwargs = {"api_key": provider.api_key, "base_url": provider.base_url}
    if timeout is not None:
        kwargs["timeout"] = timeout
    return OpenAI(**kwargs)


def model_for_api_key(api_key: str, requested_model: str) -> str:
    return resolve_llm_provider(api_key).model_for(requested_model)


def describe_llm_provider(api_key: Optional[str], *, source: str = "前端设置", requested_model: str = "deepseek-v4-flash") -> dict:
    key = validate_llm_key(api_key, source=source)
    explicit_provider, clean_key = _strip_provider_prefix(key)
    provider = resolve_llm_provider(key, source=source)
    model = provider.model_for(requested_model)
    return {
        "provider": provider.provider,
        "provider_label": provider.display_name(),
        "base_url": provider.base_url,
        "model": model,
        "key_prefix": clean_key[:3] if clean_key else "",
        "explicit_provider": explicit_provider,
    }


def probe_llm_provider(
    api_key: Optional[str],
    *,
    source: str = "前端设置",
    requested_model: str = "deepseek-v4-flash",
    timeout: float | httpx.Timeout | None = None,
) -> dict:
    key = validate_llm_key(api_key, source=source)
    provider = resolve_llm_provider(key, source=source)
    client = create_openai_client(key, timeout=timeout)
    model = provider.model_for(requested_model)
    started_at = time.perf_counter()
    response = client.chat.completions.create(
        model=model,
        extra_body={"thinking": {"type": "disabled"}},
        messages=[
            {"role": "system", "content": "你是连接测试助手，只需返回 pong。"},
            {"role": "user", "content": "ping"},
        ],
        temperature=0,
        max_tokens=4,
    )
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    content = ""
    try:
        content = response.choices[0].message.content or ""
    except (AttributeError, IndexError, KeyError, TypeError):
        content = ""
    return {
        **describe_llm_provider(key, source=source, requested_model=requested_model),
        "ok": True,
        "latency_ms": latency_ms,
        "response_preview": str(content).strip()[:80],
    }
