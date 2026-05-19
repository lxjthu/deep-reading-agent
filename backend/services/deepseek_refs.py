"""DeepSeek-based reference extraction and citation tracing service.

Replaces the pure-regex approach in backend/routers/references.py with
a model-driven pipeline validated across 4 test PDFs (157/157 refs, 0 false positives).

Usage:
    from backend.services.deepseek_refs import (
        extract_references_deepseek,
        trace_citations_deepseek,
        call_deepseek_json,
    )
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx
import json_repair
import pdfplumber
from openai import APITimeoutError, OpenAI
from backend.utils.api_key import validate_deepseek_key

logger = logging.getLogger(__name__)

MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
MAX_RETRIES = 3
DEFAULT_MAX_TOKENS = 16384

CONTINUATION_RE = re.compile(r"（\s*(?:下转|上接)\s*第\s*\d+\s*页\s*）")
REFERENCE_HEADINGS = {
    "references", "bibliography", "works cited", "参考文献",
    "参考文献（references）",
}

PROMPT_EXTRACT = """你是一个学术文献参考文献解析专家。

## 输入
你看到的是一篇学术论文 PDF 尾部提取的原始文本。由于 PDF 文本提取的限制，文本中可能存在以下问题：
- 每条参考文献可能被拆成多行（断行）
- 页眉、页码、分隔线等噪音
- 多个 PAGE BREAK 分隔不同页面的内容

## 参考文献可能使用的格式
- **编号制**：（1）、[1]、［1］、1. 等
- **作者-年份制**：作者，年份：《标题》，《期刊》第 X 期。或 Author, Year, "Title", Journal, Vol(Issue): Pages.
- **GB/T 7714 格式**：作者. 标题 [J]. 期刊, 年, 卷(期): 页码.
- 中英文参考文献混排

## 特殊情况
- 合辑 PDF 可能包含多篇论文的参考文献，此时只提取编号最连续、数量最多的那组
- 续页标记"下转第 X 页"/"上接第 X 页"应忽略，继续提取后续条目
- 英文摘要（Summary/Abstract）之后的参考文献仍然需要提取

## 任务
1. 将多行合并为完整的参考文献条目
2. 提取每条参考文献的结构化字段
3. 忽略非参考文献内容（摘要、附录、致谢、作者简介、补充材料、注释、页眉、页码等）

## 输出格式
严格 JSON：
```json
{
  "references": [
    {
      "reference_order": 1,
      "raw_text": "完整原文（合并断行后）",
      "authors": ["作者1", "作者2"],
      "year": 2020,
      "title": "论文标题",
      "journal": "期刊名",
      "volume": null,
      "issue": "期号",
      "pages": "页码范围",
      "doi": null,
      "language": "zh",
      "ignore": false,
      "ignore_reason": null
    }
  ]
}
```

## 约束
- `ignore=true` 时必须给出 `ignore_reason`（用于标记非参考文献内容）
- 不确定字段填 null，不得编造
- 保留完整 `raw_text`
- 必须提取所有参考文献条目，不要遗漏
- 程序侧会对 `ignore=false` 的条目重新编号"""

PROMPT_CITE = """你是一个学术文献引用追踪专家。

## 任务
给定一篇论文的正文和参考文献列表，找出每条参考文献在正文中的引用位置。

## 引用格式
引用可能以以下格式出现：
- 数字编号：[1]、[1,2]、[1-3]、(1)、(1,2)
- 中文编号：（1）、（1,2）
- 作者-年份：Smith (2020)、Smith and Jones (2020)
- 中文作者-年份：张三（2020）、张三和李四（2020）
- 描述性引用：according to Smith's study、as demonstrated by prior research

## 输出格式
严格 JSON：
```json
{
  "citation_traces": [
    {
      "reference_order": 1,
      "citations": [
        {
          "quote": "正文中引用该文献的原始句子片段",
          "citation_style": "numeric | author_year | descriptive",
          "location_hint": "尽力识别所在章节",
          "confidence": 0.9
        }
      ]
    }
  ]
}
```

## 约束
- quote 必须是正文的精确子串（可以从 PDF 提取的文本中找到）
- quote 尽量返回包含该引用的完整句子，不要只返回“张三（2020）”或“Smith (2020)”这类引用标记
- 不确定则不输出，宁缺毋滥
- confidence 范围 0.0-1.0
- 如果某条参考文献在正文中没有引用，citations 为空数组"""


def _normalize_ws(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "")).strip()


def _is_ref_heading(line: str) -> bool:
    stripped = _normalize_ws(line).strip(":：").lower()
    if stripped in REFERENCE_HEADINGS:
        return True
    if re.match(r"^参考文献\s*[\(（]\s*references\s*[\)）]\s*[:：]?$", stripped):
        return True
    return bool(re.match(r"^\d+(\.\d+)*\s*(references|bibliography|works cited|参考文献)$", stripped))


_NOISE_LINE_PATTERNS = [
    re.compile(r"^\d{4}\s*年第\s*\d+\s*期"),
    re.compile(r"^—+$"),
]

_ARTICLE_HEADER_RE = re.compile(r"^.{2,10}[等：:].{5,30}$")


def _is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    for pat in _NOISE_LINE_PATTERNS:
        if pat.match(s):
            return True
    if re.fullmatch(r"\d{1,5}", s):
        return True
    return False


def extract_candidate_text(pdf_path: str) -> str:
    page_sections: list[str] = []
    found_heading = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.splitlines()

            page_lines: list[str] = []
            for line in lines:
                s = _normalize_ws(line)
                if not s:
                    continue

                if not found_heading:
                    if _is_ref_heading(s):
                        found_heading = True
                    continue

                if s.lower().startswith("summary") and len(s) < 100:
                    continue

                cleaned = CONTINUATION_RE.sub("", s).strip()
                if not cleaned:
                    continue
                if _is_ref_heading(cleaned):
                    continue

                if not _is_noise_line(cleaned):
                    page_lines.append(cleaned)

            if page_lines and found_heading:
                page_sections.append("\n".join(page_lines))

    return "\n\n--- PAGE BREAK ---\n\n".join(page_sections)


def extract_body_text(pdf_path: str) -> tuple[list[dict], str]:
    body_parts: list[str] = []
    ref_lines: list[str] = []
    in_ref = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                s = _normalize_ws(line)
                if not s:
                    continue
                if not in_ref:
                    if _is_ref_heading(s):
                        in_ref = True
                        continue
                    body_parts.append(s)
                else:
                    if _is_ref_heading(s):
                        continue
                    cleaned = CONTINUATION_RE.sub("", s).strip()
                    if cleaned:
                        ref_lines.append(cleaned)

    body_text = "\n".join(body_parts)
    ref_text = "\n".join(ref_lines)

    paragraphs = []
    pid = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            blocks = re.split(r"\n\s*\n", text)
            if len(blocks) == 1:
                blocks = text.splitlines()
            for block in blocks:
                lines = [_normalize_ws(l) for l in block.splitlines() if _normalize_ws(l)]
                if not lines:
                    continue
                joined = " ".join(lines)
                if len(joined) < 30:
                    continue
                if any(_is_ref_heading(l) for l in lines):
                    break
                pid += 1
                paragraphs.append({
                    "id": pid,
                    "page_label": f"第{page_num}页",
                    "paragraph_label": f"P{page_num}-{pid}",
                    "text": joined,
                })

    return paragraphs, ref_text


def call_deepseek_json(
    messages: list[dict],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.1,
    api_key: Optional[str] = None,
) -> Optional[dict]:
    api_key = validate_deepseek_key(api_key)
    client = OpenAI(
        api_key=api_key,
        base_url=BASE_URL,
        timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0),
    )

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                extra_body={"thinking": {"type": "disabled"}},
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except (APITimeoutError, httpx.ConnectTimeout) as exc:
            logger.warning("DeepSeek timeout (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, exc)
            continue
        raw = resp.choices[0].message.content
        finish = resp.choices[0].finish_reason
        if raw and raw.strip():
            result = json_repair.repair_json(raw, return_objects=True)
            if isinstance(result, dict):
                return result
            logger.warning("DeepSeek returned non-dict JSON (attempt %d)", attempt + 1)
        else:
            logger.warning("DeepSeek empty content (attempt %d/%d), finish_reason=%s", attempt + 1, MAX_RETRIES, finish)

    return None


def extract_references_deepseek(file_path: str, api_key: Optional[str] = None) -> list[dict]:
    logger.info("Extracting references from %s", file_path)
    is_md = _is_markdown(file_path)

    if is_md:
        candidate_text = extract_candidate_text_md(file_path)
    else:
        candidate_text = extract_candidate_text(file_path)

    if len(candidate_text.strip()) < 80:
        logger.warning("Candidate text too short (%d chars), falling back to full tail", len(candidate_text))
        if is_md:
            with open(file_path, "r", encoding="utf-8") as f:
                candidate_text = f.read()
        else:
            with pdfplumber.open(file_path) as pdf:
                n = len(pdf.pages)
                start = max(0, n - 5)
                tail_pages = []
                for i in range(start, n):
                    text = pdf.pages[i].extract_text() or ""
                    tail_pages.append(text)
            candidate_text = "\n\n".join(tail_pages)

    n_lines = len(candidate_text.splitlines())
    page_break_hint = "文本中 PAGE BREAK 分隔不同页面。请合并断行，提取所有参考文献。" if not is_md else ""
    messages = [
        {"role": "system", "content": PROMPT_EXTRACT},
        {"role": "user", "content": (
            f"## 候选参考文献文本（共 {n_lines} 行）\n\n"
            f"{page_break_hint}\n\n"
            + candidate_text
        )},
    ]

    result = call_deepseek_json(messages, api_key=api_key)
    if result is None:
        logger.error("DeepSeek returned no valid JSON after %d retries", MAX_RETRIES)
        return []

    refs = result.get("references", [])
    valid = []
    for idx, r in enumerate(refs):
        if r.get("ignore"):
            logger.debug("Ignored ref: %s", r.get("ignore_reason"))
            continue
        raw_text = r.get("raw_text", "")
        language = r.get("language")
        if not language:
            language = "zh" if re.search(r"[\u4e00-\u9fff]", raw_text) else "en"
        valid.append({
            "reference_order": idx + 1,
            "raw_text": raw_text,
            "authors": r.get("authors") or [],
            "year": r.get("year"),
            "title": r.get("title"),
            "journal": r.get("journal"),
            "volume": r.get("volume"),
            "issue": r.get("issue"),
            "pages": r.get("pages"),
            "doi": r.get("doi"),
            "language": language,
        })

    for i, ref in enumerate(valid):
        ref["reference_order"] = i + 1

    logger.info("Extracted %d valid references (ignored %d)", len(valid), len(refs) - len(valid))
    return valid


def trace_citations_deepseek(
    file_path: str,
    references: list[dict],
    api_key: Optional[str] = None,
) -> list[dict]:
    if not references:
        return references

    logger.info("Tracing citations for %d references", len(references))
    is_md = _is_markdown(file_path)

    if is_md:
        paragraphs, _ref_text = extract_body_text_md(file_path)
    else:
        paragraphs, _ref_text = extract_body_text(file_path)

    body_text_parts: list[str] = []
    in_ref = False

    if is_md:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        for line in content.splitlines():
            s = _normalize_ws(line)
            if not s:
                continue
            if not in_ref:
                if _is_ref_heading(s):
                    in_ref = True
                    continue
                body_text_parts.append(s)
            else:
                if _is_ref_heading(s):
                    continue
    else:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for line in text.splitlines():
                    s = _normalize_ws(line)
                    if not s:
                        continue
                    if not in_ref:
                        if _is_ref_heading(s):
                            in_ref = True
                            continue
                        body_text_parts.append(s)
                    else:
                        if _is_ref_heading(s):
                            continue
    body_text = "\n".join(body_text_parts)

    ref_list_text = "\n".join(
        f"[{r['reference_order']}] {r.get('raw_text', '')}"
        for r in references
    )

    user_content = (
        f"## 论文正文\n\n{body_text}\n\n"
        f"## 参考文献列表\n\n{ref_list_text}\n\n"
        "请输出每条参考文献在正文中的引用链接。"
    )
    messages = [
        {"role": "system", "content": PROMPT_CITE},
        {"role": "user", "content": user_content},
    ]

    result = call_deepseek_json(messages, max_tokens=DEFAULT_MAX_TOKENS, api_key=api_key)
    if result is None:
        logger.warning("Citation tracing failed, returning references without citations")
        for ref in references:
            ref.setdefault("citations", [])
        return references

    trace_map: dict[int, list[dict]] = {}
    for trace in result.get("citation_traces", []):
        order = trace.get("reference_order", 0)
        trace_map[order] = trace.get("citations", [])

    for ref in references:
        order = ref["reference_order"]
        raw_citations = trace_map.get(order, [])
        mapped = []
        seen_citations: set[tuple[str, Optional[int]]] = set()
        for c in raw_citations:
            if (c.get("confidence") or 0) < 0.5:
                continue
            quote = c.get("quote", "")
            span = _find_quote_span(body_text, quote)
            char_start, char_end = span if span is not None else (-1, -1)
            dedup_key = (_normalize_for_match(quote), char_start if char_start >= 0 else None)
            if dedup_key in seen_citations:
                continue
            seen_citations.add(dedup_key)
            para_info = _locate_paragraph(paragraphs, body_text, char_start)
            excerpt = _build_citation_context(body_text, char_start, char_end)
            if _looks_like_reference_entry(excerpt or quote):
                continue
            mapped.append({
                "page_label": para_info.get("page_label"),
                "paragraph_label": para_info.get("paragraph_label"),
                "quote_text": quote,
                "excerpt": excerpt,
                "char_start": char_start if char_start >= 0 else None,
                "char_end": char_end if char_end >= 0 else None,
                "match_method": c.get("citation_style", "unknown"),
                "confidence": c.get("confidence"),
            })
        ref["citations"] = mapped

    total_cites = sum(len(r.get("citations", [])) for r in references)
    logger.info("Traced %d total citations for %d references", total_cites, len(references))
    return references


def _locate_paragraph(paragraphs: list[dict], body_text: str, char_pos: int) -> dict:
    if char_pos < 0:
        return {}
    offset = 0
    for p in paragraphs:
        p_len = len(p["text"])
        if offset <= char_pos < offset + p_len:
            return {"page_label": p["page_label"], "paragraph_label": p["paragraph_label"]}
        offset += p_len + 2  # +2 for \n\n separator
    return {}


def extract_candidate_text_md(md_path: str) -> str:
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()
    found_heading = False
    ref_lines: list[str] = []

    for line in lines:
        s = _normalize_ws(line)
        if not s:
            continue
        if not found_heading:
            if _is_ref_heading(s):
                found_heading = True
            continue
        if s.lower().startswith("summary") and len(s) < 100:
            continue
        cleaned = CONTINUATION_RE.sub("", s).strip()
        if not cleaned:
            continue
        if _is_ref_heading(cleaned):
            continue
        if not _is_noise_line(cleaned):
            ref_lines.append(cleaned)

    return "\n".join(ref_lines)


def extract_body_text_md(md_path: str) -> tuple[list[dict], str]:
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    body_parts: list[str] = []
    ref_lines: list[str] = []
    in_ref = False

    for line in content.splitlines():
        s = _normalize_ws(line)
        if not s:
            continue
        if not in_ref:
            if _is_ref_heading(s):
                in_ref = True
                continue
            body_parts.append(s)
        else:
            if _is_ref_heading(s):
                continue
            cleaned = CONTINUATION_RE.sub("", s).strip()
            if cleaned:
                ref_lines.append(cleaned)

    body_text = "\n".join(body_parts)
    ref_text = "\n".join(ref_lines)

    paragraphs: list[dict] = []
    pid = 0
    blocks = re.split(r"\n\s*\n", body_text)
    for block_index, block in enumerate(blocks, start=1):
        lines = [_normalize_ws(l) for l in block.splitlines() if _normalize_ws(l)]
        if not lines:
            continue
        joined = " ".join(lines)
        if len(joined) < 30:
            continue
        pid += 1
        paragraphs.append({
            "id": pid,
            "page_label": None,
            "paragraph_label": f"P{block_index}",
            "text": joined,
        })

    return paragraphs, ref_text


def _is_markdown(file_path: str) -> bool:
    return file_path.lower().endswith((".md", ".markdown"))


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _find_quote_span(text: str, quote: str) -> Optional[tuple[int, int]]:
    if not quote:
        return None

    exact = text.find(quote)
    if exact >= 0:
        return exact, exact + len(quote)

    normalized_chars: list[str] = []
    index_map: list[int] = []
    for idx, ch in enumerate(text):
        if ch.isspace():
            continue
        normalized_chars.append(ch.lower())
        index_map.append(idx)

    normalized_text = "".join(normalized_chars)
    normalized_quote = _normalize_for_match(quote)
    if not normalized_quote:
        return None

    normalized_start = normalized_text.find(normalized_quote)
    if normalized_start < 0:
        return _find_author_year_span(text, quote)

    normalized_end = normalized_start + len(normalized_quote) - 1
    return index_map[normalized_start], index_map[normalized_end] + 1


def _find_author_year_span(text: str, quote: str) -> Optional[tuple[int, int]]:
    year_match = re.search(r"(?:19|20)\d{2}", quote)
    if year_match is None:
        return None

    year = year_match.group(0)
    author_part = quote[: year_match.start()]
    author_part = author_part.strip(" \t\r\n([{（【,，;；:：、")
    author_part = re.sub(r"[([{（【,，;；:：、\s]+$", "", author_part)
    author_part = re.sub(r"(等|et\s+al\.?)$", "", author_part, flags=re.IGNORECASE).strip()
    if len(author_part) < 2:
        return None

    normalized_author = _normalize_for_match(author_part)
    for match in re.finditer(re.escape(year), text):
        window_start = max(0, match.start() - 80)
        window_end = min(len(text), match.end() + 20)
        window = text[window_start:window_end]

        normalized_chars: list[str] = []
        index_map: list[int] = []
        for offset, ch in enumerate(window):
            if ch.isspace():
                continue
            normalized_chars.append(ch.lower())
            index_map.append(window_start + offset)

        normalized_window = "".join(normalized_chars)
        author_pos = normalized_window.find(normalized_author)
        if author_pos < 0:
            continue

        start = index_map[author_pos]
        end = match.end()
        return start, end

    return None


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    sentence_end_chars = set("。！？!?；;")
    for idx, ch in enumerate(text):
        if ch not in sentence_end_chars:
            continue
        end = idx + 1
        while end < len(text) and text[end] in "\"'”’）)]} \t\r\n":
            end += 1
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _build_citation_context(text: str, start: int, end: int, *, neighbor_sentences: int = 1) -> Optional[str]:
    if start < 0 or end < 0:
        return None

    spans = _sentence_spans(text)
    if not spans:
        return _expand_excerpt(text, start, end)

    hit_index = None
    for idx, (span_start, span_end) in enumerate(spans):
        if span_start <= start < span_end or (start <= span_start and end >= span_start):
            hit_index = idx
            break
    if hit_index is None:
        return _expand_excerpt(text, start, end)

    context_start_idx = max(0, hit_index - neighbor_sentences)
    context_end_idx = min(len(spans) - 1, hit_index + neighbor_sentences)
    context_start = spans[context_start_idx][0]
    context_end = spans[context_end_idx][1]
    excerpt = re.sub(r"\s+", " ", text[context_start:context_end]).strip()
    if len(excerpt) > 900:
        return _expand_excerpt(text, start, end)
    return excerpt


def _looks_like_reference_entry(text: Optional[str]) -> bool:
    if not text:
        return False
    compact = re.sub(r"\s+", "", text)
    if re.search(r"[（(]\d{1,3}[)）].{0,120}[《\"“].{2,80}[》\"”]", compact):
        return True
    if "：《" in compact and "》，" in compact and re.search(r"(?:19|20)\d{2}", compact):
        return True
    return False


def _expand_excerpt(text: str, start: int, end: int, window: int = 180) -> Optional[str]:
    if start < 0:
        return None
    s = max(0, start - window)
    e = min(len(text), end + window)
    excerpt = text[s:e].strip()
    if len(excerpt) > 900:
        excerpt = excerpt[:900].rstrip() + "..."
    return excerpt
