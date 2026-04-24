#!/usr/bin/env python3
"""
新架构测试脚本
使用 Farmer.Chat 论文测试对话式分析引擎

运行前请设置环境变量:
    export DEEPSEEK_API_KEY='your-api-key'

或直接传入 key:
    python test_new_arch.py --key sk-xxx
"""
import sys
import argparse
from pathlib import Path

# 添加到路径
sys.path.insert(0, str(Path(__file__).parent))

from new_architecture import (
    Config, PaperCache, PaperMetadata,
    ConversationEngine, detect_paper_type, get_recommended_questions,
)


def load_paper_text(filepath: str) -> str:
    """加载论文文本"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="测试对话式论文分析引擎")
    parser.add_argument("--key", help="DeepSeek API Key（覆盖环境变量）")
    parser.add_argument("--paper", default="/tmp/paper_extract.txt", help="论文文本文件路径")
    parser.add_argument("--output", default="/tmp/new_arch_report.md", help="输出报告路径")
    parser.add_argument("--rounds", type=int, default=3, help="对话轮数")
    args = parser.parse_args()
    
    # 1. 配置
    if args.key:
        config = Config.from_key(args.key)
    else:
        try:
            config = Config.from_env()
        except ValueError as e:
            print(f"错误: {e}")
            print("请设置 DEEPSEEK_API_KEY 环境变量，或使用 --key 参数")
            sys.exit(1)
    
    print("=" * 70)
    print("对话式论文分析引擎 - 测试")
    print("=" * 70)
    
    # 2. 加载论文
    print(f"\n[1/5] 加载论文: {args.paper}")
    paper_text = load_paper_text(args.paper)
    print(f"  论文长度: {len(paper_text)} 字符")
    print(f"  预估tokens: ~{len(paper_text) // 3}")
    
    # 3. 创建论文缓存
    print(f"\n[2/5] 创建论文缓存")
    metadata = PaperMetadata(
        title="Farmer.Chat: Scaling AI-Powered Agricultural Services for Smallholder Farmers",
        authors=["Singh et al."],
        year=2024,
        source="arXiv",
        url="https://arxiv.org/abs/2409.08916",
        category="system_paper",
        tags=["HCI", "AI4D", "agriculture", "RAG", "LLM"],
    )
    cache = PaperCache(text=paper_text, metadata=metadata)
    print(f"  {cache}")
    
    # 检测论文类型
    ptype = detect_paper_type(paper_text)
    print(f"  检测到的论文类型: {ptype}")
    
    # 4. 创建对话引擎
    print(f"\n[3/5] 创建对话引擎")
    engine = ConversationEngine(config=config, paper_cache=cache)
    print(f"  模型: {config.model}")
    print(f"  API Base: {config.base_url}")
    
    # 5. 执行对话分析
    print(f"\n[4/5] 执行 {args.rounds} 轮对话分析")
    print("-" * 70)
    
    # 第一轮: 核心贡献
    print("\n>>> 第一轮: 核心贡献识别")
    q1 = "请仔细阅读这篇论文，识别其核心贡献（最多3点），并评估其创新性和最突出的局限性。"
    ans1 = engine.ask(q1, dimension="overview")
    print(f"\n{ans1[:500]}...")
    
    # 第二轮: 理论框架
    print("\n\n>>> 第二轮: 理论框架评估")
    q2 = "基于同一篇论文，分析其理论框架。论文引用了哪些理论？这些理论是否足以支撑研究设计？是否存在理论缺口？特别注意论文提出的'性别变革'框架与技术设计之间是否存在脱节。"
    ans2 = engine.ask(q2, dimension="theory")
    print(f"\n{ans2[:500]}...")
    
    # 第三轮: 方法论批判
    print("\n\n>>> 第三轮: 方法论批判")
    q3 = "继续基于同一篇论文，对其实证方法和结果进行批判性评估。论文声称'75%回答成功率'和'80%事实保真度'，但这些指标的定义是否严谨？用户研究缺乏对照组，如何证明效果？35%的超级用户贡献了80%查询，这是否说明系统触达失败？"
    ans3 = engine.ask(q3, dimension="methodology")
    print(f"\n{ans3[:500]}...")
    
    # 6. 导出报告
    print(f"\n\n[5/5] 导出结构化报告")
    engine.export_structured_report(args.output)
    
    # 成本摘要
    print(f"\n{'=' * 70}")
    print(engine.get_cost_summary())
    print(f"{'=' * 70}")
    
    print(f"\n✅ 测试完成！")
    print(f"报告保存至: {args.output}")
    print(f"完整对话历史保存在 PaperCache 中")


if __name__ == "__main__":
    main()
