"""Configuration for OpenAI-compatible LLM providers."""
import os
from dataclasses import dataclass

from backend.utils.api_key import validate_deepseek_key
from backend.utils.llm_provider import DEEPSEEK_BASE_URL, resolve_llm_provider


@dataclass
class Config:
    """LLM API configuration."""
    api_key: str
    base_url: str = DEEPSEEK_BASE_URL
    model: str = "deepseek-v4-flash"
    max_tokens: int = 8000
    temperature: float = 0.7
    timeout: int = 120

    enable_caching: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        """Read configuration from environment variables for CLI/offline scripts."""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set. Set it or pass an API key from the frontend.")
        api_key = validate_deepseek_key(api_key, source="environment variable")
        provider = resolve_llm_provider(api_key, source="environment variable")
        return cls(api_key=provider.api_key, base_url=provider.base_url, model=provider.model_for(cls.model))

    @classmethod
    def from_key(cls, api_key: str) -> "Config":
        """Create config from a user-provided API key."""
        api_key = validate_deepseek_key(api_key)
        provider = resolve_llm_provider(api_key)
        return cls(api_key=provider.api_key, base_url=provider.base_url, model=provider.model_for(cls.model))
