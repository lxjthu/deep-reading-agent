import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
import logging

import json_repair
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Page:
    number: int
    text: str

def parse_raw_page_md(raw_md_path: str) -> list[Page]:
    pages: list[Page] = []
    current_page: int | None = None
    in_text_block = False
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, current_page
        if current_page is None:
            buf = []
            return
        text = "".join(buf)
        pages.append(Page(number=current_page, text=text))
        buf = []

    with open(raw_md_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^##\s+Page\s+(\d+)\s*$", line.strip())
            if m:
                flush()
                current_page = int(m.group(1))
                in_text_block = False
                continue

            if line.strip() == "```text":
                in_text_block = True
                continue

            if line.strip() == "```" and in_text_block:
                in_text_block = False
                continue

            if in_text_block and current_page is not None:
                buf.append(line)

    flush()
    return pages

def normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")

def build_full_text_with_page_tags(pages: list[Page]) -> str:
    parts: list[str] = []
    for p in pages:
        parts.append(f"[PAGE {p.number}]\n")
        parts.append(p.text)
        if not p.text.endswith("\n"):
            parts.append("\n")
        parts.append("\n")
    return "".join(parts)

def extract_skeleton(pages: list[Page]) -> str:
    """
    Extracts a 'skeleton' of the document for long-context processing.
    Keeps:
    - [PAGE N] tags
    - Lines that look like headers (short, starts with number/caps)
    - First and last few lines of each page (context)
    Discards:
    - Long paragraph text
    """
    parts: list[str] = []
    for p in pages:
        parts.append(f"[PAGE {p.number}]\n")
        
        lines = p.text.splitlines()
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue
                
            # Heuristics to keep the line
            # 1. Short lines (potential headers)
            is_short = len(line_stripped) < 150
            # 2. Header-like patterns (1. Introduction, ABSTRACT, etc.)
            is_header_like = re.match(r"^(\d+|[A-Z]).*", line_stripped) or line_stripped.isupper() or line_stripped.endswith(":")
            # 3. Context (first 3 and last 3 lines of page)
            is_context = i < 3 or i > len(lines) - 3 
            
            if is_short or is_header_like or is_context:
                parts.append(line + "\n")
            
        parts.append("\n")
    return "".join(parts)

def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v

def call_deepseek_boundaries(text: str, is_skeleton: bool = False) -> dict:
    api_key = _env("DEEPSEEK_API_KEY")
    base_url = "https://api.deepseek.com"
    model_name = "deepseek-chat" # V3 is excellent for JSON

    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY in environment")

    client = OpenAI(api_key=api_key, base_url=base_url)

    context_desc = "summary skeleton (titles and key lines)" if is_skeleton else "full raw text"

    prompt = f"""
You will receive the {context_desc} of an academic paper (with [PAGE N] tags).

Task:
1. Extract the **actual section structure** (Top-level TOC).
   - Must include "Abstract" (if any).
   - Must include all main sections (e.g., "1 Introduction", "2 Data").
   - **MANDATORY**: Must include "References" or "Bibliography" as the last section if present.
   - Must include "Appendices" (if any).

2. For each section, identify the **exact start marker** (text snippet) and start page.
   - `start_marker`: A unique short text snippet from the document that marks the beginning (usually the title).
   - `start_page`: The page number where this marker appears.

3. **Special Handling for References**:
   - Look for "References", "Bibliography", or "Works Cited".
   - It usually appears at the end. Ensure it is captured as a separate section.

Output JSON only:
{{
  "boundaries": [
    {{"section_id": 1, "section_name": "Abstract", "start_page": 1, "start_marker": "Abstract"}},
    {{"section_id": 2, "section_name": "1. Introduction", "start_page": 2, "start_marker": "1 Introduction"}},
    ...
    {{"section_id": 9, "section_name": "References", "start_page": 25, "start_marker": "References"}}
  ],
  "notes": ["..."]
}}

Input Text:
{text}
"""

    logger.info(f"Sending request to DeepSeek ({model_name})... Text len: {len(text)}")
    
    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a precise academic structure analyzer. Output strict JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    try:
        return json_repair.repair_json(content, return_objects=True)
    except Exception:
        return {"error": "json_parse_failed", "raw": content}


def call_deepseek_direct_segment(full_text: str) -> dict:
    """
    直接分片模式：让 LLM 返回每个章节的完整内容（而非仅边界）。
    适用于需要更精确分片的场景。
    """
    api_key = _env("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY in environment")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    model_name = "deepseek-chat"

    prompt = f"""你是一位严谨的学术编辑助手。请将以下论文全文切分为标准章节结构。

任务：
1. 识别论文的所有一级章节（如 Abstract, Introduction, Data, Model, Results, Conclusion, References, Appendix 等）
2. 对每个章节，提取其完整内容（包含所有文字）
3. 记录每个章节的起始页码（从 [PAGE N] 标签推断）

输出格式（严格 JSON）：
{{
  "sections": [
    {{"id": 1, "name": "Abstract", "start_page": 1, "text": "摘要的完整文本..."}},
    {{"id": 2, "name": "1. Introduction", "start_page": 2, "text": "引言的完整文本..."}},
    ...
  ],
  "notes": ["可选的备注信息"]
}}

重要规则：
- 每个章节的 "text" 必须是该章节的完整原文，不要截断或摘要
- 如果某个章节内容很短（<200字符），考虑将其合并到相邻章节
- 保持原文格式，包括换行符
- References 章节只需包含前若干条作为示例，可适当截断（避免输出过长）

论文全文：
{full_text}
"""

    logger.info(f"Sending DIRECT SEGMENT request to DeepSeek ({model_name})... Text len: {len(full_text)}")

    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "你是严谨的学术编辑助手。只输出 JSON，不要添加任何解释。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        return json_repair.repair_json(content, return_objects=True)
    except Exception as e:
        logger.error(f"DeepSeek Direct Segment API call failed: {e}")
        return {"error": str(e)}


def locate_marker(pages: list[Page], start_page: int, marker: str) -> tuple[int, int] | None:
    if not marker:
        return None
    start_idx = max(0, start_page - 1)

    def search_range(i0: int, i1: int) -> tuple[int, int] | None:
        for i in range(i0, i1):
            text = pages[i].text
            pos = text.find(marker)
            if pos >= 0:
                return i, pos

            escaped = re.escape(marker)
            escaped = escaped.replace(r"\ ", r"\\s+")
            m = re.search(escaped, text)
            if m:
                return i, m.start()
        return None

    found = search_range(start_idx, len(pages))
    if found:
        return found

    if start_idx > 0:
        found = search_range(0, start_idx)
        if found:
            return found
    return None

def slice_segments(pages: list[Page], boundaries: list[dict]) -> list[dict]:
    boundaries_sorted = sorted(boundaries, key=lambda x: (int(x.get("start_page", 1)), int(x.get("section_id", 0))))
    segments: list[dict] = []

    located: list[tuple[int, int] | None] = []
    for b in boundaries_sorted:
        located.append(locate_marker(pages, int(b.get("start_page", 1)), str(b.get("start_marker", ""))))

    if located and located[-1] is None:
        located[-1] = (len(pages) - 1, len(pages[-1].text))

    located_raw = list(located)
    for i in range(len(located) - 2, -1, -1):
        if located[i] is None:
            located[i] = located[i + 1]

    for idx, b in enumerate(boundaries_sorted):
        start_loc = located[idx]
        end_loc = located[idx + 1] if idx + 1 < len(located) else None

        start_loc_raw = located_raw[idx] if idx < len(located_raw) else None

        if start_loc_raw is None and start_loc is not None:
            boundary_source = "filled_to_next"
        elif start_loc_raw is None:
            boundary_source = "page_fallback"
        else:
            boundary_source = "marker"

        if start_loc is None:
            start_page = max(1, int(b.get("start_page", 1)))
            start_loc = (start_page - 1, 0)

        start_page_idx, start_pos = start_loc

        if end_loc is None:
            end_page_idx = len(pages) - 1
            end_pos = len(pages[end_page_idx].text)
        else:
            end_page_idx, end_pos = end_loc

        parts: list[str] = []
        for p_i in range(start_page_idx, end_page_idx + 1):
            t = pages[p_i].text
            if p_i == start_page_idx and p_i == end_page_idx:
                parts.append(t[start_pos:end_pos])
            elif p_i == start_page_idx:
                parts.append(t[start_pos:])
            elif p_i == end_page_idx:
                parts.append(t[:end_pos])
            else:
                parts.append(t)

        seg_text = normalize_newlines("\n".join(parts))
        segments.append(
            {
                "section_id": int(b.get("section_id", idx + 1)),
                "section_name": str(b.get("section_name", "")),
                "start_page": int(b.get("start_page", 1)),
                "start_marker": str(b.get("start_marker", "")),
                "boundary_source": boundary_source,
                "text": seg_text,
            }
        )

    return segments

def render_segmented_md(raw_md_path: str, segments: list[dict], info: dict) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    header = [
        "# 论文原文结构化分段（DeepSeek 版）",
        "",
        f"- Source: {raw_md_path}",
        f"- Generated At: {now}",
        "",
    ]

    notes = info.get("notes")
    if isinstance(notes, list) and notes:
        header.append("## 说明")
        for n in notes:
            header.append(f"- {str(n)}")
        header.append("")

    out: list[str] = header
    for seg in segments:
        out.append(f"## {seg['section_id']}. {seg['section_name']}")
        out.append("")
        out.append(f"- start_page: {seg['start_page']}")
        out.append(f"- start_marker: {seg['start_marker']}")
        out.append(f"- boundary_source: {seg['boundary_source']}")
        out.append("")
        out.append("```text")
        out.append(seg["text"])
        out.append("```")
        out.append("")
    return "\n".join(out).rstrip() + "\n"

def main() -> None:
    parser = argparse.ArgumentParser(description="Segment raw per-page PDF Markdown into paper sections using DeepSeek")
    parser.add_argument("raw_md_path", help="Path to per-page raw markdown, e.g. pdf_raw_md/*_raw.md")
    parser.add_argument("--out_dir", default="pdf_segmented_md", help="Output directory")
    parser.add_argument("--direct", action="store_true", help="Use direct segment mode (LLM returns full section text)")
    args = parser.parse_args()

    pages = parse_raw_page_md(args.raw_md_path)
    if not pages:
        raise RuntimeError("No pages parsed from raw markdown")

    full_text = build_full_text_with_page_tags(pages)
    logger.info(f"Document length: {len(full_text)} characters, {len(pages)} pages")

    if args.direct:
        # ========== 直接分片模式 ==========
        logger.info("Using DIRECT SEGMENT mode (LLM returns full section content)")
        result = call_deepseek_direct_segment(full_text)
        
        if result.get("error"):
            raise RuntimeError(f"DeepSeek API error: {result['error']}")
        
        raw_sections = result.get("sections", [])
        if not raw_sections:
            raise RuntimeError("DeepSeek returned no sections")
        
        # 转换为 segments 格式
        segments = []
        for s in raw_sections:
            segments.append({
                "section_id": s.get("id", len(segments) + 1),
                "section_name": s.get("name", "Unknown"),
                "start_page": s.get("start_page", 1),
                "start_marker": s.get("name", ""),  # 直接模式用 name 作为 marker
                "boundary_source": "llm_direct",
                "text": normalize_newlines(s.get("text", "")),
            })
        deepseek_info = {"notes": result.get("notes", ["使用直接分片模式"])}
    else:
        # ========== 边界检测 + 本地切片模式（原有逻辑，保留作为 fallback） ==========
        use_skeleton = len(full_text) > 40000
        
        if use_skeleton:
            logger.info(f"Document > 40k chars. Using Skeleton Extraction for boundary detection.")
            input_text = extract_skeleton(pages)
        else:
            logger.info(f"Using Full Text for boundary detection.")
            input_text = full_text

        deepseek_info = call_deepseek_boundaries(input_text, is_skeleton=use_skeleton)

        if isinstance(deepseek_info, dict) and deepseek_info.get("error"):
            raise RuntimeError(f"DeepSeek boundary JSON parse failed: {deepseek_info.get('error')}")

        boundaries = deepseek_info.get("boundaries")
        if not isinstance(boundaries, list) or len(boundaries) == 0:
            raise RuntimeError("DeepSeek returned no boundaries.")

        segments = slice_segments(pages, boundaries)

    # Short segment warning
    for seg in segments:
        content_len = len(seg.get("text", ""))
        if content_len < 200:
            logger.warning(f"Section '{seg.get('section_name')}' is very short ({content_len} chars). Check if cut correctly.")

    logger.info(f"Segmented into {len(segments)} sections")

    os.makedirs(args.out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.raw_md_path))[0]
    out_path = os.path.join(args.out_dir, base.replace("_raw", "") + "_segmented.md")
    md = render_segmented_md(args.raw_md_path, segments, deepseek_info)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(out_path)

if __name__ == "__main__":
    main()
