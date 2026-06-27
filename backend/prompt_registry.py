from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from new_architecture.analysis_dimensions import ANALYSIS_DIMENSIONS

PROMPT_TYPE_LABELS: dict[str, str] = {
    "quant": "七步精读",
    "qual": "四步精读",
    "long": "长文本精读",
    "filter": "文献筛选",
    "compare": "对比分析",
    "synthesis": "AI 综述",
    "ai_template": "AI 模板生成",
    "translation": "全文翻译",
    "library_chat": "文献库 AI 查询",
    "journal_kb": "AI 助手顶刊名录",
    "card_note": "Markdown 卡片笔记",
    "ref_format": "参考文献格式",
    "writing_style": "\u5199\u4f5c\u98ce\u683c\u5206\u6790",
}

PROMPT_REGISTRY: dict[str, dict[str, dict[str, str]]] = {
    "quant": {
        "step_1": {"title": "Step 1: 研究概览", "file_path": "prompts/quant_analysis/step_1_overview.md"},
        "step_2": {"title": "Step 2: 理论机制", "file_path": "prompts/quant_analysis/step_2_theory.md"},
        "step_3": {"title": "Step 3: 数据说明", "file_path": "prompts/quant_analysis/step_3_data.md"},
        "step_4": {"title": "Step 4: 变量与度量", "file_path": "prompts/quant_analysis/step_4_vars.md"},
        "step_5": {"title": "Step 5: 识别策略", "file_path": "prompts/quant_analysis/step_5_identification.md"},
        "step_6": {"title": "Step 6: 结果呈现", "file_path": "prompts/quant_analysis/step_6_results.md"},
        "step_7": {"title": "Step 7: 批判性评估", "file_path": "prompts/quant_analysis/step_7_critique.md"},
    },
    "qual": {
        "L1": {"title": "L1: 背景与语境", "file_path": "prompts/qual_analysis/L1_Context_Prompt.md"},
        "L2": {"title": "L2: 理论框架", "file_path": "prompts/qual_analysis/L2_Theory_Prompt.md"},
        "L3": {"title": "L3: 论证逻辑", "file_path": "prompts/qual_analysis/L3_Logic_Prompt.md"},
        "L4": {"title": "L4: 价值与启示", "file_path": "prompts/qual_analysis/L4_Value_Prompt.md"},
    },
    "long": {
        "overview": {"title": "研究问题", "file_path": "prompts/long/overview.md"},
        "theory": {"title": "理论框架", "file_path": "prompts/long/theory.md"},
        "methodology": {"title": "识别策略", "file_path": "prompts/long/methodology.md"},
        "data_source": {"title": "数据来源", "file_path": "prompts/long/data_source.md"},
        "variable_measurement": {"title": "变量度量", "file_path": "prompts/long/variable_measurement.md"},
        "identification_assumptions": {
            "title": "识别假设",
            "file_path": "prompts/long/identification_assumptions.md",
        },
        "results": {"title": "统计结果", "file_path": "prompts/long/results.md"},
        "mechanism": {"title": "机制分析", "file_path": "prompts/long/mechanism.md"},
        "robustness": {"title": "稳健性检验", "file_path": "prompts/long/robustness.md"},
        "external_validity": {"title": "外部有效性", "file_path": "prompts/long/external_validity.md"},
        "contributions_limitations": {
            "title": "贡献与局限",
            "file_path": "prompts/long/contributions_limitations.md",
        },
        "writing_quality": {"title": "写作质量", "file_path": "prompts/long/writing_quality.md"},
        "custom": {"title": "自定义问题", "file_path": "prompts/long/custom.md"},
    },
    "filter": {
        "explorer": {"title": "探索者模式", "file_path": "prompts/literature_filter/explorer.md"},
        "reviewer": {"title": "评审者模式", "file_path": "prompts/literature_filter/reviewer.md"},
        "empiricist": {"title": "实证主义者", "file_path": "prompts/literature_filter/empiricist.md"},
    },
    "compare": {
        "ai_summary": {
            "title": "AI 文本总结",
            "file_path": "prompts/compare/ai_summary.md",
        },
    },
    "synthesis": {
        "system_role": {
            "title": "AI 综述：系统角色",
            "file_path": "prompts/synthesis/system_role.md",
        },
        "compare_system_role": {
            "title": "对比综述：系统角色",
            "file_path": "prompts/synthesis/compare_system_role.md",
        },
        "dimension_prompt": {
            "title": "AI 综述：逐维度写作指令",
            "file_path": "prompts/synthesis/dimension_prompt.md",
        },
        "single_prompt": {
            "title": "对比综述：单维度写作",
            "file_path": "prompts/synthesis/single_prompt.md",
        },
        "multi_prompt": {
            "title": "对比综述：多子问题写作",
            "file_path": "prompts/synthesis/multi_prompt.md",
        },
        "cross_dim_prompt": {
            "title": "对比综述：跨维度写作",
            "file_path": "prompts/synthesis/cross_dim_prompt.md",
        },
        "long_single_prompt": {
            "title": "长文本对比：单维度写作",
            "file_path": "prompts/synthesis/long_single_prompt.md",
        },
        "long_multi_prompt": {
            "title": "长文本对比：多维度写作",
            "file_path": "prompts/synthesis/long_multi_prompt.md",
        },
    },
    "ai_template": {
        "meta_prompt": {
            "title": "模板生成：元提示词",
            "file_path": "prompts/ai_template/meta_prompt.md",
        },
        "system_role": {
            "title": "模板生成：系统角色",
            "file_path": "prompts/ai_template/system_role.md",
        },
    },
    "translation": {
        "glossary": {
            "title": "术语词典生成",
            "file_path": "prompts/translation/glossary.md",
        },
        "restate": {
            "title": "逐块重述",
            "file_path": "prompts/translation/restate.md",
        },
    },
    "library_chat": {
        "query_parser": {
            "title": "查询解析",
            "file_path": "prompts/library_chat/query_parser.md",
        },
        "report_writer": {
            "title": "报告生成",
            "file_path": "prompts/library_chat/report_writer.md",
        },
        "tag_target_selector": {
            "title": "标签目标选择",
            "file_path": "prompts/library_chat/tag_target_selector.md",
        },
        "paper_comment_writer": {
            "title": "逐篇点评保存",
            "file_path": "prompts/library_chat/paper_comment_writer.md",
        },
    },
    "journal_kb": {
        "top_tier_registry": {
            "title": "AI 助手顶刊名录",
            "file_path": "prompts/journal_kb/top_tier_registry.md",
        },
    },
    "card_note": {
        "atomic_card_writer": {
            "title": "原子阅读卡生成",
            "file_path": "prompts/card_note/atomic_card_writer.md",
        },
    },
    "ref_format": {
        "analyze_prompt": {
            "title": "格式规则提取",
            "file_path": "prompts/ref_format/analyze_prompt.md",
        },
        "generate_prompt": {
            "title": "参考文献生成",
            "file_path": "prompts/ref_format/generate_prompt.md",
        },
    },
    "writing_style": {
        "single_fulltext_analyzer": {
            "title": "单篇全文：写法分析",
            "file_path": "prompts/writing_style/single_fulltext_analyzer.md",
        },
        "single_imitation_advisor": {
            "title": "单篇全文：模仿写作建议",
            "file_path": "prompts/writing_style/single_imitation_advisor.md",
        },
        "single_report_writer": {
            "title": "单篇全文：报告整理",
            "file_path": "prompts/writing_style/single_report_writer.md",
        },
        "batch_section_analyzer": {
            "title": "批量抽样：分节写法分析",
            "file_path": "prompts/writing_style/batch_section_analyzer.md",
        },
        "batch_imitation_advisor": {
            "title": "批量抽样：模仿写作建议",
            "file_path": "prompts/writing_style/batch_imitation_advisor.md",
        },
        "batch_comparative_synthesizer": {
            "title": "批量抽样：多篇风格对比",
            "file_path": "prompts/writing_style/batch_comparative_synthesizer.md",
        },
        "batch_report_writer": {
            "title": "批量抽样：报告整理",
            "file_path": "prompts/writing_style/batch_report_writer.md",
        },
    },
}

FILTER_FALLBACK_TEMPLATE = """你是一位学术文献筛选助手。请围绕研究主题“{topic}”评估下面这篇文献，并严格输出 JSON。

文献信息：
- 标题：{title}
- 作者：{authors}
- 期刊：{journal}
- 年份：{year}
- 摘要：{abstract}

输出 JSON 字段要求：
- score: 0-100 的相关性评分
- reason: 说明为什么相关或不相关
- abstract_cn: 摘要中文翻译；如果原文已是中文可直接整理
"""

JOURNAL_KB_FALLBACK_TEMPLATE = """# Journal Knowledge Base (Top Tier)

用于 AI 文献助手识别高质量期刊、做优先精读排序与子集筛选。请按以下格式维护：
- 每一行代表一个期刊层级
- 使用 `- **层级名称**: 期刊1, 期刊2, 缩写...`
- 逗号分隔期刊名与常用缩写

- **Economics Top 5**: American Economic Review, AER, Quarterly Journal of Economics, QJE, Journal of Political Economy, JPE, Review of Economic Studies, RES, Econometrica
- **Management UTD 24 (Selected)**: Academy of Management Journal, AMJ, Academy of Management Review, AMR, Administrative Science Quarterly, ASQ, Strategic Management Journal, SMJ, Organization Science, OrgSci, MIS Quarterly, MISQ, Information Systems Research, ISR, Marketing Science, Journal of Marketing, JM, Journal of Consumer Research, JCR
- **Finance Top 3**: Journal of Finance, Journal of Financial Economics, Review of Financial Studies
- **Chinese Top Tier**: 中国社会科学, 经济研究, 管理世界, 经济学季刊, 经济学（季刊）, 世界经济, 中国工业经济, 金融研究, 会计研究, 管理科学学报, 南开管理评论, 中国农村经济, 中国农村观察, 公共管理学报, 数量经济技术经济研究, 财贸经济, 经济学动态
- **General Science**: Nature, Science, PNAS, Proceedings of the National Academy of Sciences
"""


def get_prompt_definition(prompt_type: str, prompt_key: str) -> dict[str, str]:
    try:
        return PROMPT_REGISTRY[prompt_type][prompt_key]
    except KeyError as exc:
        raise KeyError(f"invalid prompt slot: {prompt_type}.{prompt_key}") from exc


def iter_prompt_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for prompt_type, items in PROMPT_REGISTRY.items():
        for prompt_key, meta in items.items():
            slots.append(
                {
                    "type": prompt_type,
                    "key": prompt_key,
                    "type_label": PROMPT_TYPE_LABELS[prompt_type],
                    "title": meta["title"],
                    "file_path": meta["file_path"],
                }
            )
    return slots


def get_prompt_file_path(prompt_type: str, prompt_key: str) -> Path:
    definition = get_prompt_definition(prompt_type, prompt_key)
    return PROJECT_ROOT / definition["file_path"]


def load_prompt_from_file(prompt_type: str, prompt_key: str) -> str | None:
    path = get_prompt_file_path(prompt_type, prompt_key)
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8").strip()
    return content or None


def get_builtin_fallback(prompt_type: str, prompt_key: str) -> str:
    if prompt_type == "long":
        dim = ANALYSIS_DIMENSIONS.get(prompt_key)
        if dim:
            return dim.get("system_prompt_addition", "请直接输出分析内容，不要客套开场白。")
    if prompt_type == "filter":
        return FILTER_FALLBACK_TEMPLATE
    if prompt_type == "quant":
        return f'请围绕"{get_prompt_definition(prompt_type, prompt_key)["title"]}"直接输出分析内容，不要客套开场白。'
    if prompt_type == "qual":
        return f'请围绕"{get_prompt_definition(prompt_type, prompt_key)["title"]}"直接输出分析内容，不要客套开场白。'
    if prompt_type == "compare":
        return "你是一位学术文本总结助手。请将用户选中的学术文本片段总结为一句话。要求：1.保留核心信息 2.语言简洁，不超过50个汉字 3.使用学术语言 4.不要添加原文中没有的信息"
    if prompt_type == "synthesis":
        slot_defaults = {
            "system_role": "你是一位资深的学术文献综述专家。你的任务是根据已完成的精读分析，撰写高质量的文献综述段落。你必须严格基于所提供的文献内容，不得捏造任何数据或结论。",
            "compare_system_role": "你是一位中文学术写作专家，擅长撰写规范的文献综述段落。你的任务是根据已有的精读分析内容，综合多篇文献的观点，写出适合直接插入学术论文文献综述部分的高质量文字。",
            "dimension_prompt": "【当前综述维度】{dim_label}\n\n请撰写该维度的综述段落。",
            "single_prompt": "以下是{n}篇文献在「{label}」这一问题上的精读分析内容。\n\n请综合这些文献的内容，写出**恰好一段**连贯的学术性综述文字（8～15句）。",
            "multi_prompt": "以下是{n}篇文献在「{label}」步骤下，针对以下{sub_count}个子问题的精读分析内容：{sub_questions_list}\n\n请撰写一篇结构化的分节文献综述。",
            "cross_dim_prompt": "以下是{n}篇文献在**多个分析维度**上的精读内容，涉及：{step_list}。\n\n请撰写一篇**跨维度结构化文献综述**。",
            "long_single_prompt": "以下是{n}篇文献在「{dimension}」维度上的精读分析内容。\n\n请综合这些文献，写出**恰好一段**连贯的学术性综述文字（8～15句）。",
            "long_multi_prompt": "以下是{n}篇文献在{dim_count}个维度上的精读分析内容：{dimensions}。\n\n请撰写一篇结构化的分节文献综述。",
        }
        return slot_defaults.get(prompt_key, "请直接输出分析内容，不要客套开场白。")
    if prompt_type == "ai_template":
        slot_defaults = {
            "meta_prompt": "你是一位资深的学术论文分析专家。请根据以下论文内容，设计一套系统性的案例分析维度体系。\n\n【论文内容】\n{paper_text}\n\n请设计 {dim_count} 个分析维度。",
            "system_role": "你是一个专业的学术论文分析助手，擅长设计多维度的论文精读分析框架。你必须严格按照用户要求的JSON格式输出，不要添加任何markdown标记或解释性文字。",
        }
        return slot_defaults.get(prompt_key, "请直接输出分析内容，不要客套开场白。")
    if prompt_type == "translation":
        return "请直接输出分析内容，不要客套开场白。"
    if prompt_type == "library_chat":
        return "你是一位学术文献库助手。请严格基于用户提供的文献信息完成当前任务。"
    if prompt_type == "journal_kb":
        return JOURNAL_KB_FALLBACK_TEMPLATE
    if prompt_type == "card_note":
        return """你是一位学术阅读卡片助手。请基于用户给出的论文选段、上下文和论文元数据，生成中文“原子阅读卡”。

要求：
1. 严格基于原文和上下文，不编造论文没有表达的信息。
2. 将选段压缩成一个可复用的研究笔记单元。
3. body_markdown 使用 Markdown，包含“核心观点”“依据/证据”“阅读笔记”“启发或用途”四个小节。
4. tags 输出 2-6 个短标签，不要带 #。
5. 只输出 JSON，不要输出 Markdown 代码围栏或解释。

JSON 结构：
{
  "title": "卡片标题",
  "summary": "一句话总结",
  "tags": ["标签一", "标签二"],
  "body_markdown": "## 核心观点\\n..."
}
"""
    if prompt_type == "ref_format":
        if prompt_key == "analyze_prompt":
            return "请分析参考文献示例的著录格式，并严格输出 JSON。"
        if prompt_key == "generate_prompt":
            return "请按给定格式规则将文献信息生成参考文献条目，并严格输出 JSON。"
    return "请直接输出分析内容，不要客套开场白。"
