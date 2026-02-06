#!/usr/bin/env python3
"""
PaddleOCR Segmentation Adapter

Segments PaddleOCR markdown output into academic paper sections.
Reuses DeepSeek segmentation logic but adapts to PaddleOCR's layout-aware format.
"""

import argparse
import os
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import json_repair
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _env(name: str, default: str = None) -> Optional[str]:
    """Get environment variable with fallback."""
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v


def is_paddleocr_format(content: str) -> bool:
    """
    Detect if content is from PaddleOCR extraction.

    Checks for YAML frontmatter with extractor field.
    """
    if not content.startswith("---\n"):
        return False

    # Look for extractor field in frontmatter
    end_idx = content.find("\n---\n", 4)
    if end_idx == -1:
        return False

    frontmatter = content[4:end_idx]
    return "extractor: paddleocr" in frontmatter or "extractor: pdfplumber_fallback" in frontmatter


def strip_paddleocr_artifacts(content: str) -> str:
    """
    Clean PaddleOCR artifacts from markdown for segmentation.

    Removes:
    - YAML frontmatter
    - Image div tags
    - Figure captions (standalone lines like "图1 ...")
    - Tool metadata lines
    """
    # Strip YAML frontmatter
    if content.startswith("---\n"):
        end_idx = content.find("\n---\n", 4)
        if end_idx != -1:
            content = content[end_idx + 5:]

    # Strip image HTML divs
    content = re.sub(
        r'<div[^>]*>.*?</div>',
        '',
        content,
        flags=re.DOTALL
    )

    # Strip markdown image syntax
    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)

    # Strip tool metadata line
    content = re.sub(r'\*提取工具:.*?\*\n?', '', content)

    # Strip "## Text Content" header if present
    content = re.sub(r'^## Text Content\s*\n', '', content, flags=re.MULTILINE)

    # Normalize whitespace
    content = re.sub(r'\n{3,}', '\n\n', content)

    return content.strip()


def extract_text_with_page_tags(content: str) -> str:
    """
    Convert PaddleOCR markdown to format compatible with segmentation.

    PaddleOCR outputs continuous text, so we add synthetic [PAGE N] tags
    based on content length estimation (approx 3000 chars per page).
    """
    # Clean artifacts first
    clean_text = strip_paddleocr_artifacts(content)

    # Split into synthetic pages (PaddleOCR doesn't have page markers)
    # Use approximately 3000 chars per "page" for compatibility
    chars_per_page = 3000
    parts = []
    page_num = 1

    i = 0
    while i < len(clean_text):
        # Find a good break point (paragraph boundary)
        end = min(i + chars_per_page, len(clean_text))

        # Try to break at paragraph
        if end < len(clean_text):
            # Look for paragraph break within 500 chars of target
            search_start = max(i + chars_per_page - 500, i)
            search_end = min(i + chars_per_page + 500, len(clean_text))
            search_text = clean_text[search_start:search_end]

            para_break = search_text.find('\n\n')
            if para_break != -1:
                end = search_start + para_break + 2

        page_text = clean_text[i:end].strip()
        if page_text:
            parts.append(f"[PAGE {page_num}]\n{page_text}\n")
            page_num += 1

        i = end

    return "\n".join(parts)


def call_deepseek_segment(full_text: str) -> Dict:
    """
    Call DeepSeek to segment text into academic sections.

    Reuses the direct segmentation approach from deepseek_segment_raw_md.py.
    """
    api_key = _env("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEEPSEEK_API_KEY in environment")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    model_name = "deepseek-chat"

    # Truncate text if too long (150k char limit)
    if len(full_text) > 150000:
        # Middle truncation
        keep = 70000
        full_text = full_text[:keep] + "\n\n[...中间部分省略...]\n\n" + full_text[-keep:]

    prompt = f"""你是一位严谨的学术编辑助手。请将以下论文全文切分为标准章节结构。

任务：
1. 识别论文的所有一级章节（如 Abstract, Introduction, Data, Model, Results, Conclusion, References, Appendix 等）
2. 对每个章节，提取其完整内容（包含所有文字）
3. 记录每个章节的起始页码（从 [PAGE N] 标签推断，如无标签则从1开始）

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

    logger.info(f"Sending segmentation request to DeepSeek... Text len: {len(full_text)}")

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
        parsed = json_repair.repair_json(content, return_objects=True)
        # json_repair may return a str/list instead of dict; guard against it
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"sections": parsed}
        # Last resort: try stdlib json
        import json
        return json.loads(content)
    except Exception as e:
        logger.error(f"DeepSeek Segment API call failed: {e}")
        return {"error": str(e)}


def normalize_newlines(text: str) -> str:
    """Normalize excessive newlines."""
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip("\n")


def render_segmented_md(source_path: str, segments: List[Dict], info: Dict) -> str:
    """
    Render segments to markdown format compatible with downstream pipeline.

    Output format matches deepseek_segment_raw_md.py for compatibility.
    """
    now = datetime.now().isoformat(timespec="seconds")
    header = [
        "# 论文原文结构化分段（PaddleOCR + DeepSeek）",
        "",
        f"- Source: {source_path}",
        f"- Generated At: {now}",
        "",
    ]

    notes = info.get("notes")
    if isinstance(notes, list) and notes:
        header.append("## 说明")
        for n in notes:
            header.append(f"- {str(n)}")
        header.append("")

    out = header
    for seg in segments:
        section_id = seg.get("section_id", seg.get("id", 0))
        section_name = seg.get("section_name", seg.get("name", "Unknown"))
        start_page = seg.get("start_page", 1)
        start_marker = seg.get("start_marker", section_name)
        boundary_source = seg.get("boundary_source", "llm_direct")
        text = seg.get("text", "")

        out.append(f"## {section_id}. {section_name}")
        out.append("")
        out.append(f"- start_page: {start_page}")
        out.append(f"- start_marker: {start_marker}")
        out.append(f"- boundary_source: {boundary_source}")
        out.append("")
        out.append("```text")
        out.append(text)
        out.append("```")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def segment_paddleocr_md(
    paddleocr_md_path: str,
    out_dir: str = "pdf_segmented_md"
) -> str:
    """
    Segment PaddleOCR markdown into academic sections.

    Args:
        paddleocr_md_path: Path to PaddleOCR extracted markdown
        out_dir: Output directory for segmented markdown

    Returns:
        Path to the output segmented markdown file
    """
    paddleocr_md_path = Path(paddleocr_md_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read input
    content = paddleocr_md_path.read_text(encoding="utf-8")
    logger.info(f"Loaded: {paddleocr_md_path} ({len(content)} chars)")

    # Detect and clean format
    if is_paddleocr_format(content):
        logger.info("Detected PaddleOCR format, cleaning artifacts...")
        full_text = extract_text_with_page_tags(content)
    else:
        logger.info("Non-PaddleOCR format, using content as-is...")
        full_text = content

    logger.info(f"Prepared text: {len(full_text)} chars")

    # Call DeepSeek for segmentation
    result = call_deepseek_segment(full_text)

    if not isinstance(result, dict):
        raise RuntimeError(f"Segmentation returned unexpected type ({type(result).__name__}), expected dict")

    if result.get("error"):
        raise RuntimeError(f"Segmentation failed: {result['error']}")

    raw_sections = result.get("sections", [])
    logger.info(f"DeepSeek result keys: {list(result.keys())}, "
                f"sections type: {type(raw_sections).__name__}, "
                f"sections len: {len(raw_sections) if isinstance(raw_sections, list) else 'N/A'}")
    if raw_sections and isinstance(raw_sections, list):
        logger.info(f"First section type: {type(raw_sections[0]).__name__}")
    if not raw_sections:
        raise RuntimeError("DeepSeek returned no sections")

    # Convert to standard segment format
    segments = []
    for idx, s in enumerate(raw_sections):
        if isinstance(s, str):
            # LLM sometimes returns plain strings instead of dicts
            logger.warning(f"Section {idx} is a plain string (len={len(s)}), wrapping as dict")
            s = {"id": idx + 1, "name": f"Section {idx + 1}", "text": s}
        if not isinstance(s, dict):
            logger.warning(f"Skipping non-dict section {idx}: {type(s).__name__}")
            continue
        segments.append({
            "section_id": s.get("id", len(segments) + 1),
            "section_name": s.get("name", "Unknown"),
            "start_page": s.get("start_page", 1),
            "start_marker": s.get("name", ""),
            "boundary_source": "llm_direct",
            "text": normalize_newlines(s.get("text", "")),
        })

    # Short segment warning
    for seg in segments:
        content_len = len(seg.get("text", ""))
        if content_len < 200:
            logger.warning(
                f"Section '{seg.get('section_name')}' is very short "
                f"({content_len} chars). Check if segmented correctly."
            )

    logger.info(f"Segmented into {len(segments)} sections")

    # Generate output filename
    base = paddleocr_md_path.stem
    # Remove _paddleocr suffix if present
    if base.endswith("_paddleocr"):
        base = base[:-10]

    out_path = out_dir / f"{base}_segmented.md"

    # Render and save
    md_content = render_segmented_md(str(paddleocr_md_path), segments, result)
    out_path.write_text(md_content, encoding="utf-8")

    logger.info(f"Saved segmented MD: {out_path}")
    return str(out_path)


def main():
    parser = argparse.ArgumentParser(
        description="Segment PaddleOCR markdown into academic paper sections"
    )
    parser.add_argument("paddleocr_md_path",
                        help="Path to PaddleOCR extracted markdown file")
    parser.add_argument("--out_dir", default="pdf_segmented_md",
                        help="Output directory for segmented markdown")
    args = parser.parse_args()

    if not os.path.exists(args.paddleocr_md_path):
        logger.error(f"File not found: {args.paddleocr_md_path}")
        return 1

    try:
        out_path = segment_paddleocr_md(args.paddleocr_md_path, args.out_dir)
        print(out_path)
        return 0
    except Exception as e:
        logger.error(f"Segmentation failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
