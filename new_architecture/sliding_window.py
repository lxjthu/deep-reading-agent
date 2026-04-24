"""
DeepSeek 官方缓存机制要点（基于 api-docs.deepseek.com/news/news0802）

1. 自动生效：无需代码修改，系统自动检测重复前缀
2. 前缀匹配：从第 0 个 token 开始匹配，中间开始的重复不会被缓存
3. 最小单位：64 tokens，少于 64 tokens 的内容不会被缓存
4. 不保证 100% 命中：缓存系统不保证每次都能命中
5. 缓存过期：通常几小时到几天内自动清除
6. 计费：
   - cache hit: $0.014 / 百万 tokens
   - cache miss: $0.14 / 百万 tokens

关键结论：
- 多轮对话中，如果 system + paper 部分相同，后续轮次应该能命中缓存
- 但完整消息列表（含历史 Q&A）越长，API 处理时间可能越长
- 解决方案：滑动窗口 + 本地摘要，控制每轮 API 调用的消息长度
"""

from typing import List, Dict, Optional
import json


class SlidingWindowConversation:
    """
    滑动窗口对话管理器
    
    核心策略（基于 DeepSeek 官方缓存机制设计）：
    1. 每轮 API 调用只保留最近 N 轮完整对话（默认 2 轮）
    2. 更早的对话生成本地摘要，压缩为一条消息
    3. system + paper 始终放在最前面，保持前缀一致以触发缓存
    4. 使用 streaming 模式，避免长时间等待
    5. 监控 cache hit 指标，验证缓存效果
    """
    
    def __init__(self, paper_text: str, system_prompt: str, window_size: int = 2):
        self.paper_text = paper_text
        self.system_prompt = system_prompt
        self.window_size = window_size
        self.full_history: List[Dict[str, str]] = []  # 完整历史（本地保存）
        
    def build_messages(self, new_question: str) -> List[Dict[str, str]]:
        """
        构建 API 消息列表（滑动窗口策略）
        
        结构：
        [system, paper] ← 缓存前缀（始终保持一致）
        [summary of old turns] ← 超出窗口的旧对话摘要
        [recent N turns] ← 最近 N 轮完整 Q&A
        [new_question] ← 新问题
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"[论文全文]\n{self.paper_text}\n\n以上是论文全文，请基于它回答我的问题。"},
        ]
        
        # 如果历史超出窗口，生成摘要
        total_turns = len(self.full_history) // 2
        if total_turns > self.window_size:
            old_turns = self.full_history[:-self.window_size * 2]
            summary = self._generate_summary(old_turns)
            messages.append({"role": "user", "content": f"[之前讨论的摘要]\n{summary}"})
            messages.append({"role": "assistant", "content": "我已了解之前的讨论要点，会继续基于这些背景回答。"})
        
        # 添加最近 N 轮完整对话
        recent_turns = self.full_history[-self.window_size * 2:]
        messages.extend(recent_turns)
        
        # 添加新问题
        messages.append({"role": "user", "content": new_question})
        
        return messages
    
    def _generate_summary(self, old_turns: List[Dict[str, str]]) -> str:
        """生成旧对话的摘要（本地处理）"""
        summaries = []
        for i in range(0, len(old_turns), 2):
            if i < len(old_turns):
                q = old_turns[i].get("content", "")
                # 提取前 80 字作为摘要
                q_summary = q[:80] + "..." if len(q) > 80 else q
                summaries.append(f"Q: {q_summary}")
        return "\n".join(summaries)
    
    def add_turn(self, question: str, answer: str):
        """添加一轮对话到历史"""
        self.full_history.append({"role": "user", "content": question})
        self.full_history.append({"role": "assistant", "content": answer})
    
    def get_stats(self) -> Dict:
        """获取对话统计"""
        return {
            "total_turns": len(self.full_history) // 2,
            "window_size": self.window_size,
            "paper_length": len(self.paper_text),
            "estimated_paper_tokens": len(self.paper_text) // 3,
        }


# 测试验证函数
def verify_cache_hit(usage: Dict) -> Dict:
    """
    验证缓存命中情况
    
    基于 DeepSeek API 返回的 usage 字段：
    - prompt_cache_hit_tokens: 缓存命中的 tokens
    - prompt_cache_miss_tokens: 缓存未命中的 tokens
    """
    hit = usage.get("prompt_cache_hit_tokens", 0)
    miss = usage.get("prompt_cache_miss_tokens", 0)
    total = hit + miss
    
    hit_rate = (hit / total * 100) if total > 0 else 0
    
    return {
        "hit_tokens": hit,
        "miss_tokens": miss,
        "total_tokens": total,
        "hit_rate": hit_rate,
        "saved_cost_percent": hit_rate * 0.9,  # 近似：cache hit 便宜 90%
    }
