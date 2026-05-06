from typing import Optional


def validate_deepseek_key(api_key: Optional[str], *, source: str = "前端设置") -> str:
    """
    验证并返回有效的 DeepSeek API key。

    Args:
        api_key: 用户提供的 API key（可能为 None 或空字符串）
        source: 错误提示中的来源描述，如 "前端设置" 或 "环境变量"

    Returns:
        清洗后的有效 API key 字符串

    Raises:
        ValueError: key 为空、格式错误或为占位符时抛出
    """
    if not api_key or not api_key.strip():
        raise ValueError(
            f"未提供 DeepSeek API Key。请在{source}中输入你的 Key。"
        )

    key = api_key.strip()

    if key in ("sk-xxx", "sk-xxxx", "sk-your-key", "your-api-key"):
        raise ValueError(
            f"API Key 为占位符，不可使用。"
            f"请前往 https://platform.deepseek.com/api_keys 生成新的 Key，"
            f"然后在{source}中更新。"
        )

    if not key.startswith("sk-"):
        raise ValueError(
            f"API Key 格式错误（应以 sk- 开头）。"
            f"请前往 https://platform.deepseek.com/api_keys 生成正确的 Key，"
            f"然后在{source}中更新。"
        )

    if len(key) < 20:
        raise ValueError(
            f"API Key 长度不足，可能不完整。"
            f"请前往 https://platform.deepseek.com/api_keys 重新复制完整的 Key，"
            f"然后在{source}中更新。"
        )

    return key
