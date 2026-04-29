from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from new_architecture.analysis_dimensions import ANALYSIS_DIMENSIONS

PROMPT_TYPE_LABELS: dict[str, str] = {
    "quant": "七步精读",
    "qual": "四步精读",
    "long": "长文本精读",
    "filter": "文献筛选",
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
        return f"请围绕“{get_prompt_definition(prompt_type, prompt_key)['title']}”直接输出分析内容，不要客套开场白。"
    if prompt_type == "qual":
        return f"请围绕“{get_prompt_definition(prompt_type, prompt_key)['title']}”直接输出分析内容，不要客套开场白。"
    return "请直接输出分析内容，不要客套开场白。"
