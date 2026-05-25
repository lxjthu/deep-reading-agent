from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from services.deepseek_refs import call_deepseek_json, extract_references_deepseek


DEFAULT_BATCH_SIZE = 30

ANALYZE_PROMPT = """你是一位学术参考文献格式分析专家。

## 任务
分析下面提供的参考文献列表，提取出该列表所遵循的参考文献著录格式规则。

## 输出格式
严格 JSON：
{
  "format_name": "识别出的格式名称",
  "rules": "用自然语言完整描述格式规则，使另一位编辑能仅凭此描述完全复现该格式",
  "special_notes": "需要注意的特殊情况"
}

## 约束
- 规则描述必须精确到标点符号级别。
- 如果示例中同时包含中英文文献，分别描述两种格式。
- 不确定的地方标注“视情况而定”而非猜测。
"""

GENERATE_PROMPT = """你是一位学术参考文献著录专家。请严格按照给定的格式规则，将提供的文献信息格式化为参考文献条目。

## 输出要求
1. 每条文献生成一行参考文献文本。
2. 严格遵循给定格式规则中的标点、空格和字段顺序。
3. 如果某些字段缺失，按该格式惯例处理，不要编造事实。
4. 按提供的 order 顺序编号。
5. 只输出 JSON，不添加解释性文字。

## 输出格式
{
  "references": [
    {"order": 1, "formatted": "格式化后的完整参考文献文本"}
  ]
}
"""


@dataclass(frozen=True)
class BibEntryForFormat:
    id: str
    title: str
    authors: list[str]
    year: int | None = None
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    language: str | None = None


def serialize_bib_entry(entry: BibEntryForFormat, order: int) -> dict[str, Any]:
    return {
        "order": order,
        "id": entry.id,
        "title": entry.title,
        "authors": entry.authors,
        "year": entry.year,
        "journal": entry.journal,
        "volume": entry.volume,
        "issue": entry.issue,
        "pages": entry.pages,
        "doi": entry.doi,
        "language": entry.language,
    }


def refs_to_text(references: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, ref in enumerate(references, start=1):
        raw = str(ref.get("raw_text") or "").strip()
        if raw:
            lines.append(raw)
            continue
        title = str(ref.get("title") or "").strip()
        authors = ref.get("authors") or []
        author_text = ", ".join(str(item) for item in authors if item)
        year = ref.get("year") or ""
        journal = str(ref.get("journal") or "").strip()
        fallback = ". ".join(part for part in [author_text, str(year), title, journal] if part)
        if fallback:
            lines.append(f"[{index}] {fallback}")
    return "\n".join(lines)


def analyze_reference_format_from_text(
    text: str,
    *,
    api_key: str,
) -> dict[str, Any]:
    cleaned = text.strip()
    if len(cleaned) < 80:
        raise ValueError("参考文献示例文本过短，请粘贴完整的参考文献列表。")

    result = call_deepseek_json(
        [
            {"role": "system", "content": ANALYZE_PROMPT},
            {"role": "user", "content": cleaned[:20000]},
        ],
        api_key=api_key,
        max_tokens=4096,
        temperature=0.1,
    )
    if result is None:
        raise RuntimeError("AI 服务暂时不可用，请稍后重试。")

    format_name = str(result.get("format_name") or "自定义参考文献格式").strip()
    rules = result.get("rules") or result.get("format_rules") or ""
    special_notes = result.get("special_notes") or ""
    format_rules = json.dumps(
        {
            "rules": str(rules).strip(),
            "special_notes": str(special_notes).strip(),
        },
        ensure_ascii=False,
    )
    samples = [line.strip() for line in cleaned.splitlines() if line.strip()][:5]
    return {
        "format_name": format_name,
        "format_rules": format_rules,
        "raw_references_count": max(1, len(samples)),
        "raw_references_sample": samples,
        "source_text_truncated": cleaned[:3000],
    }


def analyze_reference_format_from_file(file_path: str, *, api_key: str) -> dict[str, Any]:
    references = extract_references_deepseek(file_path, api_key=api_key)
    text = refs_to_text(references)
    if len(text.strip()) < 80:
        raise ValueError("未能从文件中定位参考文献区域，请尝试直接粘贴文本。")
    result = analyze_reference_format_from_text(text, api_key=api_key)
    result["raw_references_count"] = len(references)
    result["raw_references_sample"] = [line.strip() for line in text.splitlines() if line.strip()][:5]
    result["source_text_truncated"] = text[:3000]
    return result


def _strip_leading_number(value: str) -> str:
    return re.sub(r"^\s*(?:\[\d+\]|\d+[.)、])\s*", "", value).strip()


def generate_formatted_references(
    entries: list[BibEntryForFormat],
    *,
    format_rules: str,
    format_name: str | None,
    api_key: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> str:
    if not entries:
        raise ValueError("请选择至少一篇文献。")
    if not format_rules.strip():
        raise ValueError("缺少参考文献格式规则。")

    formatted: list[str] = []
    for offset in range(0, len(entries), batch_size):
        batch = entries[offset : offset + batch_size]
        payload = [serialize_bib_entry(entry, offset + index + 1) for index, entry in enumerate(batch)]
        user_content = (
            f"## 格式名称\n{format_name or '自定义参考文献格式'}\n\n"
            f"## 格式规则\n{format_rules}\n\n"
            f"## 文献信息 JSON\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        result = call_deepseek_json(
            [
                {"role": "system", "content": GENERATE_PROMPT},
                {"role": "user", "content": user_content},
            ],
            api_key=api_key,
            max_tokens=8192,
            temperature=0.1,
        )
        if result is None:
            raise RuntimeError("AI 服务暂时不可用，请稍后重试。")
        rows = result.get("references") or []
        if not isinstance(rows, list):
            raise RuntimeError("AI 返回的参考文献格式无效。")
        for row in rows:
            if isinstance(row, dict):
                text = str(row.get("formatted") or "").strip()
            else:
                text = str(row).strip()
            if text:
                formatted.append(_strip_leading_number(text))

    if not formatted:
        raise RuntimeError("AI 未生成可用的参考文献目录。")
    return "\n".join(f"[{index}] {text}" for index, text in enumerate(formatted, start=1))
