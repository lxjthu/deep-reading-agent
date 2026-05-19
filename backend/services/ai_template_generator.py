import json
from typing import Optional

import httpx
from openai import OpenAI
from json_repair import loads as repair_json_loads

from backend.utils.api_key import validate_deepseek_key

MODEL = "deepseek-chat"
DEFAULT_MAX_TOKENS = 4000
MAX_TEMPLATE_TOKENS = 12000
MAX_PAPER_CHARS = 8000

META_PROMPT_TEMPLATE = """你是一位资深的学术论文分析专家。请根据以下论文内容，设计一套系统性的案例分析维度体系。

【论文内容】
{paper_text}

【任务说明】
1. 先对论文进行快速解析，识别：学科归属、研究类型、理论传统、核心变量(X→Y)、方法论特征
2. 基于识别结果，从以下维度池中选择最适合该论文的 {dim_count} 个维度：

   参考维度池（根据论文特征从中选择最相关的，也可以自创维度）：
   - 案例研究类：案例选择逻辑、案例呈现方式、过程追踪
   - 定量实证类：识别策略与内生性处理、统计结果解读、稳健性检验
   - 制度分析类：制度情境与历史脉络、规则体系分析、治理结构
   - 网络/关系类：社会网络结构、社会资本类型、嵌入性分析
   - 产业经济类：市场结构、价值链治理、产业政策
   - 公共资源类：行动情境边界、设计原则对照、多中心治理
   - 政策评估类：政策含义与实践转化、政策因果识别

3. 为每个维度生成完整的提示词

【输出格式】
严格按以下 JSON 输出，不要添加任何解释或markdown标记：

{{
  "paper_analysis": {{
    "discipline": "一级学科—二级学科",
    "research_type": "研究类型",
    "theory_tradition": "理论传统",
    "core_x": "解释变量",
    "core_y": "被解释变量",
    "methodology": "方法论特征"
  }},
  "template": {{
    "name": "模板名称（学科+研究类型+分析框架）",
    "description": "该模板适用于什么类型的论文",
    "category": "案例研究/定量实证/混合方法/理论建构",
    "dimension_count": 12
  }},
  "dimensions": [
    {{
      "dim_name": "维度名称（6-12字，专业术语）",
      "description": "分析焦点（20-40字）",
      "default_question": "默认分析问题",
      "prompt_content": "【分析维度：维度名称】\\n\\n默认问题\\n\\n要求：\\n1. 子问题1（事实识别：引用原文段落/数据/方法）\\n2. 子问题2（逻辑评估：判断论证是否成立）\\n3. 子问题3（批判判断：指出潜在缺陷或替代解释）\\n4. 直接输出分析，不做铺垫性表述",
      "group_name": "核心维度/方法论维度/理论维度/批判维度",
      "rationale": "为什么选这个维度的简要说明"
    }}
  ]
}}

【质量规范】
1. 维度名称使用学科专业术语，避免通用表达
2. 子问题从"事实识别→逻辑评估→批判判断"递进
3. 至少一个维度包含对典型方法论缺陷的质疑
4. 全篇术语统一，使用同一理论传统的话语体系
5. 维度之间互补不重复
6. 维度总数控制在 {dim_count} 个左右（±2）"""


def generate_template_from_paper(
    paper_text: str,
    api_key: str,
    dim_count: int = 12,
) -> dict:
    api_key = validate_deepseek_key(api_key)
    text = paper_text[:MAX_PAPER_CHARS]

    meta_prompt = META_PROMPT_TEMPLATE.format(
        paper_text=text,
        dim_count=dim_count,
    )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0),
    )

    token_budget = _max_tokens_for_dimension_count(dim_count)
    budgets = [token_budget]
    if token_budget < MAX_TEMPLATE_TOKENS:
        budgets.append(MAX_TEMPLATE_TOKENS)

    last_content = ""
    last_finish_reason = None
    for budget in budgets:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的学术论文分析助手，擅长设计多维度的论文精读分析框架。你必须严格按照用户要求的JSON格式输出，不要添加任何markdown标记或解释性文字。",
                },
                {"role": "user", "content": meta_prompt},
            ],
            temperature=0.7,
            max_tokens=budget,
        )

        choice = response.choices[0]
        content = choice.message.content or ""
        last_content = content
        last_finish_reason = getattr(choice, "finish_reason", None)
        parsed = _parse_json_response(content)
        if parsed is not None:
            return parsed
        if last_finish_reason != "length":
            break

    if last_finish_reason == "length":
        return {
            "error": "JSON解析失败：模型输出过长被截断，请减少维度数或稍后重试",
            "raw_content": last_content[:500],
        }
    return {"error": "JSON解析失败", "raw_content": last_content[:500]}


def _max_tokens_for_dimension_count(dim_count: int) -> int:
    return min(MAX_TEMPLATE_TOKENS, max(DEFAULT_MAX_TOKENS, dim_count * 650))


def _extract_json_text(content: str) -> str:
    if "```json" in content:
        return content.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in content:
        return content.split("```", 1)[1].split("```", 1)[0].strip()
    return content.strip()


def _parse_json_response(content: str) -> Optional[dict]:
    if not content:
        return None
    json_str = _extract_json_text(content)
    try:
        parsed = json.loads(json_str)
    except (json.JSONDecodeError, IndexError):
        try:
            parsed = repair_json_loads(json_str)
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None
