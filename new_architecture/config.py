"""配置管理 - API密钥和模型参数"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """DeepSeek API配置"""
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    max_tokens: int = 8000
    temperature: float = 0.7
    timeout: int = 120  # 请求超时秒数
    
    # Prompt caching 相关
    enable_caching: bool = True  # 是否尝试利用prompt caching
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量读取配置"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY未设置。请设置环境变量:\n"
                "  export DEEPSEEK_API_KEY='your-api-key'"
            )
        return cls(api_key=api_key)
    
    @classmethod
    def from_key(cls, api_key: str) -> "Config":
        """直接传入API key（测试用）"""
        return cls(api_key=api_key)
