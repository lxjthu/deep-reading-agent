from typing import Optional

from backend.utils.llm_provider import validate_llm_key


def validate_deepseek_key(api_key: Optional[str], *, source: str = "前端设置") -> str:
    """Backward-compatible API key validator for DeepSeek and MiMo-compatible keys."""
    return validate_llm_key(api_key, source=source)
