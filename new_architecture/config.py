"""配置管理 - API密钥和模型参数"""
import os
from dataclasses import dataclass
from typing import Optional
from backend.utils.api_key import validate_deepseek_key


@dataclass
class Config:
    """DeepSeek API配置"""
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    max_tokens: int = 8000
    temperature: float = 0.7
    timeout: int = 120
    
    enable_caching: bool = True
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量读取配置（CLI/离线脚本用）"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY 未设置。请设置环境变量或通过前端传入 API Key。"
            )
        return cls(api_key=validate_deepseek_key(api_key, source="环境变量"))
    
    @classmethod
    def from_key(cls, api_key: str) -> "Config":
        """直接传入API key（前端用户 key）"""
        return cls(api_key=validate_deepseek_key(api_key))
