"""对话式分析引擎 - 核心模块"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass

from openai import OpenAI

from .config import Config
from .paper_cache import PaperCache
from .analysis_dimensions import ANALYSIS_DIMENSIONS


@dataclass
class TurnResult:
    """单轮对话结果"""
    question: str
    answer: str
    dimension: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    

class ConversationEngine:
    """
    对话式论文分析引擎
    
    核心职责:
    1. 管理论文缓存和对话历史
    2. 构建API消息列表（利用prompt caching）
    3. 执行分析维度（按需调用）
    4. 导出结构化结果
    """
    
    # 系统提示词 - 定义AI的角色和分析标准
    SYSTEM_PROMPT = """你是一位严谨的学术论文分析专家。

你的分析风格:
1. 批判性思维：既肯定优点，也指出不足
2. 具体性：引用论文的具体段落、数据、方法论细节，避免泛泛而谈
3. 结构化：使用清晰的标题、列表和表格组织分析
4. 建设性：不仅批评，还要提出改进建议

分析原则:
- 核心贡献：最多识别3点，避免过度扩展
- 理论评估：区分论文引用的理论和未引用但相关的理论
- 方法批判：区分"作者的方法选择"和"方法执行质量"
- 因果推断：严格评估因果识别的可靠性
- 实践意义：区分"对领域的启示"和"对政策的建议"

输出要求:
- 直接输出分析内容，不要"好的""作为..."等客套开场白
- 使用中文回答，关键术语保留英文原文（首次出现时）
- 使用 Markdown 格式（标题、列表、表格）
"""
    
    def __init__(
        self,
        config: Config,
        paper_cache: PaperCache,
        max_history_turns: int = 2,
        prompt_overrides: Optional[Dict[str, str]] = None,
    ):
        self.config = config
        self.paper_cache = paper_cache
        # 使用长超时 (180-300s) 以支持大上下文 + 缓存匹配
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=300,  # 关键：大上下文需要更长超时
        )
        self.results: List[TurnResult] = []
        self.max_history_turns = max_history_turns  # 滑动窗口大小
        self.prompt_overrides = prompt_overrides or {}
        
    def _load_prompt_from_file(self, dimension: str) -> Optional[str]:
        """尝试从 prompts/long/ 目录加载维度提示词"""
        override = (self.prompt_overrides.get(dimension) or "").strip()
        if override:
            return override

        import sys as _sys
        if getattr(_sys, "frozen", False):
            base_dir = Path(_sys._MEIPASS)
        else:
            base_dir = Path(__file__).resolve().parents[1]
        prompt_path = base_dir / "prompts" / "long" / f"{dimension}.md"
        if prompt_path.exists():
            content = prompt_path.read_text(encoding="utf-8").strip()
            if content:
                return content
        return None
    
    def _build_messages(self, question: str, dimension: Optional[str] = None) -> List[Dict[str, str]]:
        """
        构建API消息列表（优化缓存命中率）
        
        缓存策略：
        - 论文全文放在 user 消息中（而非 system），DeepSeek 缓存对 user 消息前缀生效
        - 当 max_history_turns=0 时，不携带历史，每步独立调用，缓存命中率最高
        """
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
        ]
        
        # 论文全文 - 放在 user 消息中，这是会被缓存的固定前缀
        paper_prefix = self.paper_cache.get_full_prompt_prefix()
        messages.append({"role": "user", "content": paper_prefix})
        
        # 滑动窗口：只保留最近 N 轮完整对话
        history = self.paper_cache.conversation_history
        total_turns = len(history) // 2
        
        if self.max_history_turns == 0:
            # 不携带任何历史，每步独立调用，缓存前缀 100% 一致
            pass
        elif total_turns > self.max_history_turns:
            # 超出窗口的旧对话生成摘要
            old_turns = history[:-self.max_history_turns * 2]
            summary = self._generate_summary(old_turns)
            messages.append({"role": "user", "content": f"[之前讨论的摘要]\n{summary}"})
            messages.append({"role": "assistant", "content": "我已了解之前的讨论要点。"})
            # 添加最近 N 轮
            recent_turns = history[-self.max_history_turns * 2:]
            for turn in recent_turns:
                messages.append({"role": turn["role"], "content": turn["content"]})
        else:
            # 全部保留
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})
        
        # 新问题（可选附加维度说明）
        if dimension and dimension in ANALYSIS_DIMENSIONS:
            dim_info = ANALYSIS_DIMENSIONS[dimension]
            # 优先从文件加载提示词
            file_prompt = self._load_prompt_from_file(dimension)
            if file_prompt:
                enhanced_question = f"【分析维度：{dim_info['name']}】\n{file_prompt}\n\n{question}"
            else:
                enhanced_question = f"【分析维度：{dim_info['name']}】\n{dim_info['system_prompt_addition']}\n\n{question}"
        else:
            enhanced_question = question
            
        messages.append({"role": "user", "content": enhanced_question})
        
        return messages
    
    def _generate_summary(self, old_turns: List[Dict[str, str]]) -> str:
        """生成旧对话的摘要（本地处理）"""
        summaries = []
        for i in range(0, len(old_turns), 2):
            if i < len(old_turns):
                q = old_turns[i].get("content", "")
                q_summary = q[:100] + "..." if len(q) > 100 else q
                summaries.append(f"Q: {q_summary}")
        return "\n".join(summaries)
    
    def ask(self, question: str, dimension: Optional[str] = None) -> str:
        """
        提出一个问题，获取回答
        
        核心流程:
        1. 构建完整消息列表（滑动窗口）
        2. 调用DeepSeek API（长超时）
        3. 保存对话历史
        4. 返回结果
        """
        messages = self._build_messages(question, dimension)
        
        # 显示上下文信息
        total_chars = sum(len(m["content"]) for m in messages)
        print(f"  [Context] {len(messages)} messages, ~{total_chars//3} tokens")
        
        try:
            start_time = __import__('time').time()
            response = self.client.chat.completions.create(
                model=self.config.model,
                extra_body={"thinking": {"type": "disabled"}},
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            elapsed = __import__('time').time() - start_time
            
            answer = response.choices[0].message.content
            usage = response.usage
            
            # 显示缓存命中情况
            if usage:
                hit = getattr(usage, 'prompt_cache_hit_tokens', 0)
                miss = getattr(usage, 'prompt_cache_miss_tokens', 0)
                total = hit + miss
                if total > 0:
                    rate = hit / total * 100
                    print(f"  [Cache] hit={hit}, miss={miss}, rate={rate:.1f}% ({elapsed:.1f}s)")
            
            # 记录结果
            turn = TurnResult(
                question=question,
                answer=answer,
                dimension=dimension,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            )
            self.results.append(turn)
            self.paper_cache.add_turn(question, answer, dimension)
            
            return answer
            
        except Exception as e:
            error_msg = f"API调用失败: {str(e)}"
            print(f"[错误] {error_msg}")
            self.results.append(TurnResult(
                question=question,
                answer=error_msg,
                dimension=dimension,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            ))
            return error_msg
    
    def analyze_dimension(
        self,
        dimension: str,
        custom_question: Optional[str] = None,
        dim_meta: Optional[Dict] = None,
    ) -> str:
        if dimension in ANALYSIS_DIMENSIONS:
            dim_info = ANALYSIS_DIMENSIONS[dimension]
            question = custom_question or (dim_info["default_questions"][0] if dim_info["default_questions"] else "请分析这个维度。")
            print(f"\n[分析维度: {dim_info['name']}] {question}")
            return self.ask(question, dimension)
        elif dim_meta:
            question = custom_question or dim_meta.get("default_question", "请分析这个维度。")
            dim_name = dim_meta.get("dim_name", dimension)
            prompt_content = dim_meta.get("prompt_content", "")
            enhanced = f"【分析维度：{dim_name}】\n{prompt_content}\n\n{question}" if prompt_content else f"【分析维度：{dim_name}】\n{question}"
            print(f"\n[分析维度: {dim_name}] {question}")
            return self.ask(enhanced, dimension=None)
        else:
            return f"未知维度: {dimension}"
    
    def run_full_analysis(self, dimensions: Optional[List[str]] = None) -> Dict[str, str]:
        """
        运行完整的多维度分析
        """
        if dimensions is None:
            dimensions = ["overview", "theory", "methodology", "results", "limitations"]
        
        results = {}
        for dim in dimensions:
            print(f"\n{'='*60}")
            print(f"正在分析: {ANALYSIS_DIMENSIONS.get(dim, {}).get('name', dim)}")
            print(f"{'='*60}")
            
            answer = self.analyze_dimension(dim)
            results[dim] = answer
            
            if self.results:
                last = self.results[-1]
                print(f"[Token] Prompt: {last.prompt_tokens}, Completion: {last.completion_tokens}, Total: {last.total_tokens}")
        
        return results
    
    def export_structured_report(self, filepath: str):
        """
        导出结构化分析报告（Markdown格式，适合Obsidian）
        """
        lines = [
            f"# 论文分析报告: {self.paper_cache.metadata.title}",
            "",
            "## 论文信息",
            f"- **标题**: {self.paper_cache.metadata.title}",
            f"- **作者**: {', '.join(self.paper_cache.metadata.authors)}",
            f"- **年份**: {self.paper_cache.metadata.year or 'N/A'}",
            f"- **来源**: {self.paper_cache.metadata.source}",
            f"- **URL**: {self.paper_cache.metadata.url}",
            f"- **论文长度**: ~{self.paper_cache.estimated_tokens} tokens",
            "",
            "## 分析摘要",
            f"- **分析轮数**: {len(self.results)}",
            f"- **总Token消耗**: {sum(r.total_tokens for r in self.results)}",
            "",
            "---",
            "",
        ]
        
        # 按维度分组输出
        for result in self.results:
            dim_name = ANALYSIS_DIMENSIONS.get(result.dimension, {}).get("name", result.dimension or "一般问题")
            lines.extend([
                f"## {dim_name}",
                "",
                f"**问题**: {result.question}",
                "",
                "**回答**:",
                "",
                result.answer,
                "",
                f"*(Token: {result.total_tokens})*",
                "",
                "---",
                "",
            ])
        
        report = "\n".join(lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n报告已导出: {filepath}")
        return report
    
    def get_cost_summary(self) -> str:
        """获取成本摘要"""
        total_prompt = sum(r.prompt_tokens for r in self.results)
        total_completion = sum(r.completion_tokens for r in self.results)
        total = total_prompt + total_completion
        
        # DeepSeek定价（参考）
        # Prompt: $0.14/1M tokens (cache miss), $0.014/1M (cache hit)
        # Completion: $0.28/1M tokens
        cost_prompt = total_prompt / 1_000_000 * 0.14
        cost_completion = total_completion / 1_000_000 * 0.28
        cost_total = cost_prompt + cost_completion
        
        return f"""
成本估算:
- Prompt tokens: {total_prompt:,} (~${cost_prompt:.4f})
- Completion tokens: {total_completion:,} (~${cost_completion:.4f})
- Total tokens: {total:,}
- 预估总成本: ~${cost_total:.4f} (USD)

注: 如果prompt caching生效，论文部分的tokens成本会降低90%（$0.014/1M vs $0.14/1M）
"""
