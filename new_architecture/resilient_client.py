"""
Resilient DeepSeek API Client with Streaming and Retry
解决多轮对话中的超时/挂起问题
"""
import requests
import json
import time
from typing import List, Dict, Optional, Callable


class ResilientDeepSeekClient:
    """
    弹性 DeepSeek API 客户端
    
    核心策略:
    1. 使用 requests 直接调用（绕过 OpenAI 客户端可能的 bug）
    2. 每轮使用独立 HTTP 连接（避免连接池污染）
    3. 流式传输 + 短超时 + 重试
    4. 对话历史滑动窗口（防止上下文无限增长）
    5. 本地摘要机制（保留关键信息，丢弃冗余）
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        })
        
    def _call_api_streaming(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 8000,
        temperature: float = 0.7,
        timeout: int = 60,
        max_retries: int = 3,
    ) -> str:
        """
        调用 API（流式 + 重试）
        
        参数:
            timeout: 单轮超时秒数（默认60秒）
            max_retries: 最大重试次数
        """
        data = {
            "model": "deepseek-v4-flash",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        
        for attempt in range(max_retries):
            start = time.time()
            print(f"    [API Call] Attempt {attempt + 1}/{max_retries}, timeout={timeout}s")
            
            try:
                # 使用独立的连接（禁用 keep-alive 避免污染）
                resp = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=data,
                    timeout=(10, timeout),  # (connect_timeout, read_timeout)
                    stream=True,
                    headers={"Connection": "close"},  # 每轮关闭连接
                )
                
                if resp.status_code != 200:
                    error_text = resp.text[:200]
                    print(f"    [Error] HTTP {resp.status_code}: {error_text}")
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt  # 指数退避
                        print(f"    [Retry] Waiting {wait}s...")
                        time.sleep(wait)
                        continue
                    return f"[API Error {resp.status_code}: {error_text}]"
                
                # 解析流式响应
                content = ""
                token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                
                for line in resp.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            chunk = line[6:]
                            if chunk == "[DONE]":
                                break
                            try:
                                obj = json.loads(chunk)
                                delta = obj["choices"][0]["delta"].get("content", "")
                                content += delta
                                
                                # 检查 usage（通常在最后一个 chunk）
                                if "usage" in obj and obj["usage"]:
                                    token_usage = obj["usage"]
                            except:
                                pass
                
                elapsed = time.time() - start
                print(f"    [Success] {elapsed:.1f}s, {len(content)} chars")
                if token_usage.get("total_tokens"):
                    print(f"    [Tokens] prompt={token_usage.get('prompt_tokens')}, "
                          f"completion={token_usage.get('completion_tokens')}, "
                          f"total={token_usage.get('total_tokens')}")
                
                return content
                
            except requests.exceptions.Timeout:
                print(f"    [Timeout] Call timed out after {timeout}s")
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"    [Retry] Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    return "[Error: API timeout after all retries]"
                    
            except Exception as e:
                print(f"    [Error] {type(e).__name__}: {str(e)[:100]}")
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"    [Retry] Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    return f"[Error: {str(e)[:100]}]"
        
        return "[Error: All retries exhausted]"
    
    def chat_round(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 8000,
        temperature: float = 0.7,
    ) -> str:
        """执行单轮对话（带完整错误处理）"""
        return self._call_api_streaming(messages, max_tokens, temperature)


class ConversationManager:
    """
    对话管理器 - 解决上下文增长导致的超时问题
    
    核心策略:
    1. 滑动窗口: 保留最近 N 轮对话（默认 3 轮）
    2. 本地摘要: 对超出窗口的旧对话进行摘要压缩
    3. 每轮独立: 每轮 API 调用包含 [system, paper, 摘要, 当前问题]
    """
    
    def __init__(self, client: ResilientDeepSeekClient, paper_text: str, system_prompt: str):
        self.client = client
        self.paper_text = paper_text
        self.system_prompt = system_prompt
        self.history: List[Dict[str, str]] = []  # 完整历史（本地保存）
        self.max_history_turns = 3  # 滑动窗口大小
        
    def _build_messages(self, question: str, include_summary: bool = True) -> List[Dict[str, str]]:
        """
        构建 API 消息列表
        
        结构:
        1. system prompt
        2. paper full text（缓存部分）
        3. [可选] 历史摘要（超出窗口的旧对话）
        4. 最近 N 轮完整对话
        5. 当前问题
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"[论文全文]\n{self.paper_text}\n\n以上是论文全文，请基于它回答我的问题。"},
        ]
        
        # 如果历史超出窗口，生成摘要
        if len(self.history) > self.max_history_turns * 2 and include_summary:
            # 超出窗口的旧对话
            old_turns = self.history[:-self.max_history_turns * 2]
            # 生成简要摘要（或直接使用预设摘要）
            summary = self._generate_summary(old_turns)
            messages.append({"role": "user", "content": f"[之前讨论摘要]\n{summary}"})
            messages.append({"role": "assistant", "content": "我已了解之前的讨论要点。"})
        
        # 添加最近 N 轮完整对话
        recent_turns = self.history[-self.max_history_turns * 2:]
        messages.extend(recent_turns)
        
        # 添加当前问题
        messages.append({"role": "user", "content": question})
        
        return messages
    
    def _generate_summary(self, old_turns: List[Dict[str, str]]) -> str:
        """
        对旧对话生成摘要（本地处理，不调用 API）
        简单实现：提取关键信息
        """
        # 简单策略：保留用户问题，截断助手回答
        summary_parts = []
        for i in range(0, len(old_turns), 2):
            if i < len(old_turns):
                q = old_turns[i].get("content", "")[:100]  # 截断问题
                summary_parts.append(f"Q: {q}...")
        return "\n".join(summary_parts)
    
    def ask(self, question: str, max_tokens: int = 8000) -> str:
        """
        提问并获取回答
        
        流程:
        1. 构建消息（滑动窗口）
        2. 调用 API（弹性客户端）
        3. 保存到历史
        4. 返回结果
        """
        messages = self._build_messages(question)
        
        # 估算 token 数（调试）
        total_chars = sum(len(m["content"]) for m in messages)
        print(f"  [Context] {len(messages)} messages, {total_chars} chars, ~{total_chars//3} tokens")
        
        # 调用 API
        answer = self.client.chat_round(messages, max_tokens)
        
        # 保存历史
        self.history.append({"role": "user", "content": question})
        self.history.append({"role": "assistant", "content": answer})
        
        return answer
    
    def get_history_summary(self) -> str:
        """获取完整对话历史的文本摘要"""
        lines = []
        for i, turn in enumerate(self.history):
            role = "Q" if turn["role"] == "user" else "A"
            content = turn["content"][:150] + "..." if len(turn["content"]) > 150 else turn["content"]
            lines.append(f"{role}{i//2+1}: {content}")
        return "\n".join(lines)


# 便捷函数
def create_conversation(api_key: str, paper_text: str, system_prompt: Optional[str] = None) -> ConversationManager:
    """快速创建对话管理器"""
    if system_prompt is None:
        system_prompt = """你是一位学术论文分析专家，专长在人机交互（HCI）、信息通信技术与发展（ICT4D）、发展经济学和人工智能领域。

分析风格:
1. 批判性思维：既肯定优点，也指出不足
2. 具体性：引用论文的具体段落、数据、方法论细节
3. 结构化：使用清晰的标题、列表和表格
4. 建设性：不仅批评，还要提出改进建议

请用中文回答，关键术语保留英文原文。"""
    
    client = ResilientDeepSeekClient(api_key)
    return ConversationManager(client, paper_text, system_prompt)
