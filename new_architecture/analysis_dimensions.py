"""分析维度定义 - 从"死步骤"变为"检查清单"""
from typing import Dict, List, Optional


# 分析维度检查清单
# 用户/系统可以按需调用，不按固定顺序
ANALYSIS_DIMENSIONS = {
    "overview": {
        "name": "核心贡献识别",
        "description": "论文解决了什么问题？创新点在哪里？",
        "default_questions": [
            "这篇论文的核心贡献是什么？（最多3点）",
            "与现有研究相比，其创新性在哪里？",
            "最突出的局限性是什么？",
        ],
        "system_prompt_addition": "请聚焦核心贡献，避免泛泛而谈。",
    },
    "theory": {
        "name": "理论框架评估",
        "description": "引用了哪些理论？是否存在理论缺口？",
        "default_questions": [
            "论文引用了哪些核心理论？",
            "这些理论是否足以支撑其研究设计？",
            "是否存在理论缺口或理论误用？",
        ],
        "system_prompt_addition": "请具体指出理论来源、适用性和缺口。",
    },
    "methodology": {
        "name": "方法论批判",
        "description": "研究方法是否合理？因果推断是否可靠？",
        "default_questions": [
            "研究方法是否合理？",
            "因果推断策略是什么？是否满足条件独立性？",
            "数据是否充分？是否存在选择偏差？",
        ],
        "system_prompt_addition": "请严格评估方法论，指出所有潜在偏差。",
    },
    "results": {
        "name": "实证结果解读",
        "description": "数据是否充分？统计显著性？效应大小？",
        "default_questions": [
            "关键实证结果是什么？",
            "统计显著性如何？效应大小是否具有实际意义？",
            "结果对样本选择是否敏感？",
        ],
        "system_prompt_addition": "请聚焦数据本身，避免过度解读。",
    },
    "limitations": {
        "name": "局限性分析",
        "description": "作者承认了哪些局限？还有哪些没提到？",
        "default_questions": [
            "作者自己承认了哪些局限？",
            "还有哪些局限性作者没有提到？",
            "这些局限性对结论的可靠性有多大影响？",
        ],
        "system_prompt_addition": "请区分作者自述局限和你发现的额外局限。",
    },
    "implications": {
        "name": "实践意义",
        "description": "对领域、政策、实践有什么启示？",
        "default_questions": [
            "这项研究对该领域有什么启示？",
            "对政策制定者有什么建议？",
            "对实践者有什么 actionable 的建议？",
        ],
        "system_prompt_addition": "请提供具体、可操作的启示。",
    },
    "comparison": {
        "name": "跨文献对比",
        "description": "与相关工作相比，增量贡献是什么？",
        "default_questions": [
            "与相关工作相比，关键区别是什么？",
            "这篇论文的增量贡献是什么？",
            "如果引用这篇论文，应该在什么场景下引用？",
        ],
        "system_prompt_addition": "请具体对比，避免泛泛而谈。",
    },
    "future": {
        "name": "未来方向",
        "description": "如果让你继续这项研究，你会怎么做？",
        "default_questions": [
            "如果让你继续这项研究，你会怎么做？",
            "下一步最关键的实证工作是什么？",
            "还有哪些研究问题没有被回答？",
        ],
        "system_prompt_addition": "请提供具体、可行的研究建议。",
    },
}


# 论文类型自动检测关键词
PAPER_TYPE_KEYWORDS = {
    "system_paper": ["chatbot", "system", "framework", "architecture", "design", "implementation", "deploy"],
    "econometrics": ["regression", "causal", "instrumental variable", "RCT", "difference-in-differences", "panel data"],
    "theory": ["model", "equilibrium", "optimization", "proof", "theorem", "proposition"],
    "experiment": ["experiment", "lab", "field", "randomized", "treatment", "control"],
    "survey": ["survey", "questionnaire", "interview", "focus group", "qualitative"],
}


def detect_paper_type(text: str) -> str:
    """基于文本关键词检测论文类型"""
    text_lower = text.lower()
    scores = {}
    for ptype, keywords in PAPER_TYPE_KEYWORDS.items():
        scores[ptype] = sum(1 for kw in keywords if kw in text_lower)
    
    if max(scores.values()) == 0:
        return "general"
    return max(scores, key=scores.get)


def get_recommended_questions(paper_type: str) -> List[str]:
    """基于论文类型生成推荐问题"""
    type_questions = {
        "system_paper": [
            "这篇系统的核心创新是什么？与现有方案的关键区别？",
            "系统的用户研究是否存在选择偏差？如何改进？",
            "论文声称'提升效率'，但缺乏因果证据。你会如何设计对照实验？",
            "系统的可扩展性瓶颈在哪里？",
        ],
        "econometrics": [
            "识别策略是什么？是否满足条件独立性假设？",
            "工具变量是否有效？是否存在弱工具变量问题？",
            "结果对样本选择敏感吗？尝试安慰剂检验。",
            "模型设定是否合理？是否存在遗漏变量偏差？",
        ],
        "theory": [
            "核心假设是什么？放松哪些假设会导致结论失效？",
            "模型的预测能力如何？是否有实证验证？",
            "与现有理论的关系：补充、扩展还是挑战？",
        ],
        "experiment": [
            "实验设计是否合理？是否存在 Hawthorne 效应？",
            "样本量是否足够？统计功效是多少？",
            "结果的外部有效性如何？",
        ],
        "survey": [
            "抽样策略是否合理？是否存在覆盖偏差？",
            "问卷设计是否存在引导性问题？",
            "定性数据到定量结论的转换是否可靠？",
        ],
        "general": [
            "这篇论文的核心贡献是什么？",
            "方法论有什么亮点和不足？",
            "如果你来改进这项研究，会怎么做？",
        ],
    }
    return type_questions.get(paper_type, type_questions["general"])
