from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any


SOURCE_EVIDENCE_BLOCK_START = "<!--SOURCE_EVIDENCE_JSON"
SOURCE_EVIDENCE_BLOCK_END = "SOURCE_EVIDENCE_JSON-->"

SOURCE_EVIDENCE_INSTRUCTION = f"""

【隐藏原文证据要求】
在正常 Markdown 回答之后，追加一个 HTML 注释块。注释块不会展示给用户，只用于系统保存证据。
格式必须严格如下：
{SOURCE_EVIDENCE_BLOCK_START}
{{"items":[{{"claim":"一句中文概括","quote":"逐字摘自论文全文的原文片段","evidence_role":"method|data|finding|limitation|theory|background|contradiction","section_hint":"原文章节线索","page_hint":"页码线索或空字符串","confidence":"high|medium|low"}}]}}
{SOURCE_EVIDENCE_BLOCK_END}

规则：
1. quote 必须逐字来自上方论文全文，不得翻译、改写或补写。
2. 每个维度最多给 5 条最关键证据。
3. 如果找不到逐字原文证据，items 输出空数组。
4. 正文部分不要提及这个隐藏注释块。
"""


def split_answer_and_evidence(raw_answer: str) -> tuple[str, list[dict[str, Any]], str | None]:
    if SOURCE_EVIDENCE_BLOCK_START not in raw_answer:
        return raw_answer, [], None

    start = raw_answer.find(SOURCE_EVIDENCE_BLOCK_START)
    end = raw_answer.find(SOURCE_EVIDENCE_BLOCK_END, start)
    if end < 0:
        return raw_answer[:start].strip(), [], "missing_evidence_block_end"

    answer = raw_answer[:start].strip()
    block_start = start + len(SOURCE_EVIDENCE_BLOCK_START)
    block = raw_answer[block_start:end].strip()
    try:
        payload = json.loads(block)
    except json.JSONDecodeError as exc:
        return answer, [], f"invalid_json: {exc}"

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return answer, [], "items_not_list"

    candidates: list[dict[str, Any]] = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        if not quote:
            continue
        candidates.append(
            {
                "claim": str(item.get("claim") or "").strip(),
                "quote": quote,
                "evidence_role": str(item.get("evidence_role") or "support").strip(),
                "section_hint": str(item.get("section_hint") or "").strip(),
                "page_hint": str(item.get("page_hint") or "").strip(),
                "confidence": str(item.get("confidence") or "").strip(),
            }
        )
    return answer, candidates, None


def _normalize_for_match(text: str) -> str:
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _hash_text(text: str) -> str:
    return hashlib.sha256(_normalize_for_match(text).encode("utf-8")).hexdigest()


def _find_exact(paper_text: str, quote: str) -> tuple[int | None, int | None]:
    if not quote:
        return None, None
    pos = paper_text.find(quote)
    if pos >= 0:
        return pos, pos + len(quote)
    normalized_paper = _normalize_for_match(paper_text)
    normalized_quote = _normalize_for_match(quote)
    pos = normalized_paper.find(normalized_quote)
    if pos >= 0:
        return pos, pos + len(normalized_quote)
    return None, None


def _best_fuzzy_window(paper_text: str, quote: str) -> tuple[int | None, int | None, float]:
    normalized_quote = _normalize_for_match(quote)
    if len(normalized_quote) < 30:
        return None, None, 0.0
    window_size = max(len(normalized_quote) + 80, 240)
    step = max(40, window_size // 4)
    best_score = 0.0
    best_start: int | None = None
    best_end: int | None = None
    for start in range(0, max(len(paper_text) - 1, 1), step):
        window = paper_text[start : start + window_size]
        if not window:
            break
        score = SequenceMatcher(None, _normalize_for_match(window), normalized_quote).ratio()
        if score > best_score:
            best_score = score
            best_start = start
            best_end = min(len(paper_text), start + len(window))
    return best_start, best_end, round(best_score, 4)


def validate_source_evidence_candidates(
    candidates: list[dict[str, Any]],
    *,
    paper_text: str,
    max_records: int = 5,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for candidate in candidates:
        if len(records) >= max_records:
            break
        quote = str(candidate.get("quote") or "").strip()
        if len(quote) < 20:
            continue
        quote_hash = _hash_text(quote)
        if quote_hash in seen_hashes:
            continue
        seen_hashes.add(quote_hash)

        start, end = _find_exact(paper_text, quote)
        validation_status = "exact" if start is not None else "unmatched"
        match_score = 1.0 if start is not None else 0.0
        source_tier = "P0" if start is not None else "P2"

        if start is None:
            fuzzy_start, fuzzy_end, fuzzy_score = _best_fuzzy_window(paper_text, quote)
            if fuzzy_score >= 0.86:
                start = fuzzy_start
                end = fuzzy_end
                validation_status = "fuzzy"
                match_score = fuzzy_score
                source_tier = "P0"

        records.append(
            {
                "claim_text": str(candidate.get("claim") or "").strip(),
                "quote_text": quote,
                "quote_hash": quote_hash,
                "evidence_role": str(candidate.get("evidence_role") or "support").strip(),
                "section_hint": str(candidate.get("section_hint") or "").strip(),
                "page_label": str(candidate.get("page_hint") or "").strip() or None,
                "validation_status": validation_status,
                "match_score": match_score,
                "source_tier": source_tier,
                "char_start": start,
                "char_end": end,
                "metadata": {
                    "model_confidence": str(candidate.get("confidence") or "").strip(),
                },
            }
        )
    return records
