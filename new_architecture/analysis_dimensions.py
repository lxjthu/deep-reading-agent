"""分析维度定义 - 从"死步骤"变为"检查清单"""
from typing import Dict, List, Optional


# 分析维度检查清单 - 12个标准维度
# 用户/系统可以按需调用，不按固定顺序
ANALYSIS_DIMENSIONS = {
    "overview": {
        "name": "研究问题",
        "description": "论文解决了什么问题？创新点在哪里？",
        "default_questions": [
            "这篇论文的核心研究问题是什么？",
            "与现有研究相比，其创新性在哪里？",
            "最突出的局限性是什么？",
        ],
        "system_prompt_addition": "请聚焦核心研究问题，避免泛泛而谈。",
    },
    "theory": {
        "name": "理论框架",
        "description": "引用了哪些理论？是否存在理论缺口？",
        "default_questions": [
            "论文引用了哪些核心理论？",
            "这些理论是否足以支撑其研究设计？",
            "是否存在理论缺口或理论误用？",
        ],
        "system_prompt_addition": "请具体指出理论来源、适用性和缺口。",
    },
    "methodology": {
        "name": "识别策略",
        "description": "研究方法是否合理？因果推断是否可靠？",
        "default_questions": [
            "研究方法是否合理？",
            "因果推断策略是什么？是否满足条件独立性？",
            "数据是否充分？是否存在选择偏差？",
        ],
        "system_prompt_addition": "请严格评估方法论，指出所有潜在偏差。",
    },
    "data_source": {
        "name": "数据来源",
        "description": "数据从哪里获取？是否具有代表性？",
        "default_questions": [
            "数据从哪里获取？",
            "样本是否具有代表性？",
            "数据质量如何？是否存在缺失或测量误差？",
        ],
        "system_prompt_addition": "请评估数据来源的可靠性和代表性。",
    },
    "variable_measurement": {
        "name": "变量度量",
        "description": "关键变量如何度量？是否存在测量误差？",
        "default_questions": [
            "关键变量如何度量？",
            "测量方法是否可靠？",
            "是否存在测量误差或代理变量问题？",
        ],
        "system_prompt_addition": "请评估变量度量的准确性和合理性。",
    },
    "identification_assumptions": {
        "name": "识别假设",
        "description": "因果识别所依赖的关键假设是什么？是否可信？",
        "default_questions": [
            "因果识别所依赖的关键假设是什么？",
            "这些假设是否可信？",
            "如果假设不成立，结论会如何变化？",
        ],
        "system_prompt_addition": "请严格评估识别假设的可信度和稳健性。",
    },
    "results": {
        "name": "统计结果",
        "description": "数据是否充分？统计显著性？效应大小？",
        "default_questions": [
            "关键实证结果是什么？",
            "统计显著性如何？效应大小是否具有实际意义？",
            "结果对样本选择是否敏感？",
        ],
        "system_prompt_addition": "请聚焦数据本身，避免过度解读。",
    },
    "mechanism": {
        "name": "机制分析",
        "description": "论文是否分析了作用机制？机制证据是否充分？",
        "default_questions": [
            "论文是否分析了作用机制？",
            "机制证据是否充分？",
            "是否存在其他可能的解释机制？",
        ],
        "system_prompt_addition": "请评估机制分析的深度和证据强度。",
    },
    "robustness": {
        "name": "稳健性检验",
        "description": "结果是否通过了稳健性检验？",
        "default_questions": [
            "作者做了哪些稳健性检验？",
            "结果是否对不同模型设定敏感？",
            "是否考虑了异质性效应？",
        ],
        "system_prompt_addition": "请评估稳健性检验的全面性和说服力。",
    },
    "external_validity": {
        "name": "外部有效性",
        "description": "结果能否推广到其他场景？",
        "default_questions": [
            "结果能否推广到其他场景？",
            "样本的外部有效性如何？",
            "在不同群体或时期是否依然成立？",
        ],
        "system_prompt_addition": "请评估结果的外部有效性和推广范围。",
    },
    "contributions_limitations": {
        "name": "贡献与局限",
        "description": "论文的核心贡献和主要局限是什么？",
        "default_questions": [
            "论文的核心贡献是什么？（最多3点）",
            "主要局限性有哪些？",
            "这些局限性对结论的可靠性有多大影响？",
        ],
        "system_prompt_addition": "请平衡评价贡献和局限。",
    },
    "writing_quality": {
        "name": "写作质量",
        "description": "论文的写作和论证质量如何？",
        "default_questions": [
            "论文的结构是否清晰？",
            "论证逻辑是否严密？",
            "图表和表述是否准确易懂？",
        ],
        "system_prompt_addition": "请评估写作质量和论证清晰度。",
    },
    "custom": {
        "name": "自定义问题",
        "description": "用户自定义的分析问题",
        "default_questions": [
            "请回答用户的自定义问题。",
        ],
        "system_prompt_addition": "请根据用户的问题进行分析，直接输出分析内容。",
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
