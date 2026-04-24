"""论文缓存管理 - 负责论文全文的存储和缓存"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import json


@dataclass
class PaperMetadata:
    """论文元数据"""
    title: str
    authors: List[str]
    year: Optional[int] = None
    source: str = ""  # arXiv, NBER, etc.
    url: str = ""
    category: str = ""  # econometrics, system_design, theory, etc.
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "source": self.source,
            "url": self.url,
            "category": self.category,
            "tags": self.tags,
        }


class PaperCache:
    """
    论文全文缓存管理器
    
    核心职责:
    1. 存储论文完整文本
    2. 管理元数据
    3. 提供文本切片（如果论文超长）
    4. 追踪对话历史
    """
    
    def __init__(self, text: str, metadata: PaperMetadata):
        self.text = text
        self.metadata = metadata
        self.conversation_history: List[Dict[str, str]] = []
        
        # 估算token数（粗略: 1 token ≈ 4 chars for English, 1.5 for Chinese）
        self.estimated_tokens = len(text) // 3
        
    @property
    def is_long_paper(self) -> bool:
        """判断是否为超长论文（超过DeepSeek 64K上下文限制）"""
        return self.estimated_tokens > 60000  # 留余量给system prompt和对话历史
    
    def get_truncated_text(self, max_tokens: int = 50000) -> str:
        """
        如果论文超长，返回截断版本（保留核心章节）
        策略: 保留 Abstract + Introduction + Conclusion + 每章开头
        """
        if not self.is_long_paper:
            return self.text
            
        # 简单截断策略：取前 max_tokens*3 字符
        # TODO: 更智能的切片（基于章节标题）
        return self.text[:max_tokens * 3] + "\n\n[论文剩余部分已截断...]"
    
    def add_turn(self, question: str, answer: str, dimension: Optional[str] = None):
        """添加一轮对话到历史（API消息格式）"""
        self.conversation_history.append({
            "role": "user",
            "content": question,
            "dimension": dimension,
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": answer,
        })
    
    def get_full_prompt_prefix(self) -> str:
        """
        获取用于API调用的论文全文前缀
        这是会被缓存的部分
        """
        return f"[论文信息]\n标题: {self.metadata.title}\n作者: {', '.join(self.metadata.authors)}\n\n[论文全文]\n{self.text}"
    
    def export_conversation(self, filepath: str):
        """导出完整对话记录到JSON"""
        data = {
            "metadata": self.metadata.to_dict(),
            "estimated_tokens": self.estimated_tokens,
            "conversation": self.conversation_history,
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def __repr__(self):
        return f"PaperCache({self.metadata.title}, {self.estimated_tokens} tokens, {len(self.conversation_history)} turns)"
