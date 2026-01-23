import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime

import json_repair
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


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


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v


def call_kimi_boundaries(full_text: str, model: str | None = None) -> dict:
    api_key = _env("OPENAI_API_KEY")
    base_url = _env("OPENAI_BASE_URL", "https://api.moonshot.cn/v1")
    model_name = model or _env("OPENAI_MODEL", "moonshot-v1-auto")

    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in environment")

    client = OpenAI(api_key=api_key, base_url=base_url)

    prompt = f"""
你将收到一篇论文的逐页原文（带有 [PAGE N] 标签）。

任务：
1) 你需要把论文原文按结构分割成 7 个部分：
   1. 引言（introduction 相关内容）
   2. 文献回顾
   3. 理论与假说
   4. 数据获取与清洗
   5. 变量与测量
   6. 识别策略与实证分析
   7. 结论与讨论

2) 你只需要输出每个部分的“起始标记”（start_marker）与对应起始页码（start_page）。
   - start_marker 必须是原文中“可直接匹配到的连续文本片段”，并且尽量是一行内的短字符串（建议用章节/小节标题行）。
   - start_marker 尽量不要包含跨行断开的长句；长度建议 <= 80 个字符。
   - 优先选择类似："1 Introduction"、"2 Institutional Background and Data Description"、"3 Peer Effects on App Usage"、"7 Conclusion" 这样的标题。
   - 不要改写、不总结，不要输出正文。
   - 如果某部分没有独立章节（例如文献回顾融合在引言里），也必须给一个最合理的起始标记（可以是小节标题或一个短句段首）。

输出：只返回严格 JSON（不要 markdown），格式如下：
{{
  "boundaries": [
    {{"section_id": 1, "section_name": "引言", "start_page": 1, "start_marker": "..."}},
    ... 共 7 条 ...
  ],
  "notes": ["..."]
}}

原文：
{full_text}
"""

    resp = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "你是严谨的学术编辑助手。只输出 JSON。"},
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


def render_segmented_md(raw_md_path: str, segments: list[dict], kimi_info: dict) -> str:
    now = datetime.now().isoformat(timespec="seconds")
    header = [
        "# 论文原文结构化分段（Kimi 自然结构版）",
        "",
        f"- Source: {raw_md_path}",
        f"- Generated At: {now}",
        "",
    ]

    notes = kimi_info.get("notes")
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
    parser = argparse.ArgumentParser(description="Segment raw per-page PDF Markdown into 7 paper sections using Kimi")
    parser.add_argument("raw_md_path", help="Path to per-page raw markdown, e.g. pdf_raw_md/*_raw.md")
    parser.add_argument("--out_dir", default="pdf_segmented_md", help="Output directory")
    parser.add_argument("--model", default=None, help="Override model name")
    args = parser.parse_args()

    pages = parse_raw_page_md(args.raw_md_path)
    if not pages:
        raise RuntimeError("No pages parsed from raw markdown")

    full_text = build_full_text_with_page_tags(pages)
    kimi_info = call_kimi_boundaries(full_text, model=args.model)

    if isinstance(kimi_info, dict) and kimi_info.get("error"):
        raise RuntimeError(f"Kimi boundary JSON parse failed: {kimi_info.get('error')}")

    boundaries = kimi_info.get("boundaries")
    if not isinstance(boundaries, list) or len(boundaries) != 7:
        raise RuntimeError("Kimi must return exactly 7 boundaries in boundaries[]")

    segments = slice_segments(pages, boundaries)

    os.makedirs(args.out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.raw_md_path))[0]
    out_path = os.path.join(args.out_dir, base.replace("_raw", "") + "_segmented.md")
    md = render_segmented_md(args.raw_md_path, segments, kimi_info)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(out_path)


if __name__ == "__main__":
    main()
