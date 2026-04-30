"""Test DeepSeek on complex multi-paper PDF with interleaved references."""
from __future__ import annotations

import json, os, re, sys, time
from pathlib import Path
import json_repair
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

load_dotenv()
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"

def normalize_ws(v): return re.sub(r"\s+", " ", (v or "")).strip()

REFERENCE_HEADINGS = {"references", "bibliography", "works cited", "参考文献", "参考文献（references）"}

def is_reference_heading(line):
    stripped = normalize_ws(line).strip(":：").lower()
    if stripped in REFERENCE_HEADINGS:
        return True
    if re.match(r"^参考文献\s*[\(（]\s*references\s*[\)）]\s*[:：]?$", stripped):
        return True
    return bool(re.match(r"^\d+(\.\d+)*\s*(references|bibliography|works cited|参考文献)$", stripped))

CONTINUATION_RE = re.compile(r"（\s*(?:下转|上接)\s*第\s*\d+\s*页\s*）")


def clean_continuation_markers(text):
    return CONTINUATION_RE.sub("", text)


NON_REF_PATTERNS = [
    re.compile(r"^--\s*\d+"),              # page numbers like "-- 133"
    re.compile(r"^VI-\s*\d+"),             # appendix page numbers
    re.compile(r"^《\s*管理世界\s*》"),      # journal header
    re.compile(r"^\d{4}\s*年第\s*\d+\s*期"),  # journal issue info
    re.compile(r"^(Abstract|Keywords|JEL)\s*[:：]?", re.I),  # English abstract sections
    re.compile(r"^\(?\d+\.\d+", ),           # decimal numbers (table data)
]


def looks_like_table_data(line):
    s = line.strip()
    if re.match(r"^(变量|样本|均值|标准差|最小值|最大值|中位数|Observations|Adjusted|Panel|Constant|Controls|Yes|No|资料来源|作者整理)", s):
        return True
    if re.match(r"^\d+\s*$", s) and len(s) < 5:
        return True
    if re.match(r"^\d+\s*\.\d+\s*$", s):
        return True
    if re.match(r"^\*{1,3}$", s):
        return True
    return False


def looks_like_ref_entry(line):
    s = line.strip()
    if re.match(r"^[（(\［[]\s*\d+\s*[）)\］]]", s):
        return True
    return False


def extract_ref_text(pdf_path):
    reader = PdfReader(pdf_path)
    sections = []
    current_lines = []
    in_ref = False
    found_main_refs = False

    for page in reader.pages:
        text = page.extract_text() or ""
        lines = text.splitlines()
        for line in lines:
            s = normalize_ws(line)
            if not s:
                continue
            if not in_ref:
                if is_reference_heading(s):
                    in_ref = True
                    found_main_refs = True
                    continue
            else:
                cleaned = clean_continuation_markers(s).strip()
                if not cleaned:
                    continue
                if is_reference_heading(cleaned):
                    if current_lines:
                        sections.append("\n".join(current_lines))
                        current_lines = []
                    continue
                current_lines.append(cleaned)
    if current_lines:
        sections.append("\n".join(current_lines))

    all_text = "\n\n--- SECTION BREAK ---\n\n".join(sections)

    filtered_lines = []
    for line in all_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if looks_like_ref_entry(s):
            filtered_lines.append(s)
            continue
        skip = False
        for pat in NON_REF_PATTERNS:
            if pat.match(s):
                skip = True
                break
        if skip:
            continue
        if looks_like_table_data(s):
            continue
        if len(s) < 15 and not looks_like_ref_entry(s):
            continue
        if re.match(r"^(附录|Appendix)\s*(表|图|Table|Figure|\d)", s, re.I):
            continue
        filtered_lines.append(s)

    return "\n".join(filtered_lines)


PROMPT_COMPLEX = """你是一个学术文献参考文献解析专家。

## 重要背景
你看到的文本来自一本中文学术期刊的合辑 PDF。这种 PDF 中通常包含多篇论文，因此尾部区域可能混杂多篇论文的参考文献。

你需要做的是：
1. **识别出哪些参考文献属于同一篇论文**（通过编号连续性、主题一致性判断）
2. **只提取编号最连续、数量最多的那组参考文献**（这通常就是目标论文的参考文献）
3. 忽略属于其他论文的参考文献（编号不连续、主题完全不同）
4. 忽略所有非参考文献内容（摘要、附录、致谢、作者简介、英文摘要、补充材料、注释等）

## 关键：续页标记
中文学术期刊常有"下转第 X 页"和"上接第 X 页"标记，这意味着参考文献**跨越了其他论文的内容**。例如：
- 参考文献从 (1) 到 (49)，中间出现"下转第 133 页"
- 接着是一整块属于另一篇论文的内容（标题、摘要、参考文献 (34)-(45) 等）
- 然后出现"上接第 116 页"，后续的参考文献 (50)、(51)、(52) 仍属于目标论文

**你必须跨越其他论文的整块内容，继续查找目标论文的后续参考文献。**

## 识别策略
1. **编号连续性**：目标论文的编号是最长的连续序列，即使中间被其他论文打断
2. **主题一致性**：目标论文的参考文献主题应与正文中出现的高频词（如"人工智能"、"企业生产率"等）一致
3. **跨论文检测**：当遇到一个编号范围（如 (34)-(45)）与当前序列不连续，且主题完全不同（如平台并购、市场竞争），说明这是另一篇论文的内容，应标记为 ignore 并跳过整个块
4. **不要遗漏续页后的参考文献**：在"上接第 X 页"之后出现的编号 (50)、(51) 等仍属于目标论文

## 输出格式
严格 JSON：
```json
{
  "references": [
    {
      "reference_order": 1,
      "raw_text": "完整原文",
      "authors": ["作者1", "作者2"],
      "year": 2020,
      "title": "标题",
      "journal": "期刊",
      "volume": null,
      "issue": null,
      "pages": null,
      "doi": null,
      "language": "zh",
      "ignore": false,
      "ignore_reason": null
    }
  ]
}
```

## 约束
- `ignore=true` 时必须给出 `ignore_reason`（如"属于另一篇论文"、"是摘要"等）
- 不确定字段填 null，不要编造
- 保留完整 `raw_text`
- 目标论文的 `ignore` 必须为 `false`
- **完整性要求**：目标论文通常有 40-60 条参考文献。你必须提取出所有带编号 (N) 的条目，不要遗漏任何一条。如果你提取的数量少于 45 条，说明你遗漏了续页后的参考文献。"""


def run(pdf_path):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=BASE_URL)
    stem = Path(pdf_path).stem

    print(f"=== Complex PDF Test: {stem} ===\n")
    print("[1/2] Extracting reference candidate text...")
    ref_text = extract_ref_text(pdf_path)
    print(f"  Candidate text: {len(ref_text)} chars\n")

    print("[2/2] Calling DeepSeek with complex PDF prompt...")
    text_lines = ref_text.splitlines()
    user_content = (
        f"## 候选参考文献文本（共 {len(text_lines)} 行）\n\n"
        "注意：文本中有多个 SECTION BREAK 分隔不同的区域。请仔细扫描全文，包括续页后的内容。目标论文的参考文献约有 50-52 条。\n\n"
        + ref_text
    )
    messages = [
        {"role": "system", "content": PROMPT_COMPLEX},
        {"role": "user", "content": user_content},
    ]
    for attempt in range(3):
        resp = client.chat.completions.create(
            model=MODEL,
            extra_body={"thinking": {"type": "disabled"}},
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=16384,
        )
        raw = resp.choices[0].message.content
        print(f"  Attempt {attempt+1}: {len(raw) if raw else 0} chars, finish_reason={resp.choices[0].finish_reason}")
        if raw and raw.strip():
            break
        print(f"  Empty content (attempt {attempt+1}/3)")

    result = json_repair.repair_json(raw, return_objects=True)
    refs = result.get("references", []) if isinstance(result, dict) else []
    valid = [r for r in refs if not r.get("ignore")]
    ignored = [r for r in refs if r.get("ignore")]

    print(f"\n{'='*60}")
    print(f"RESULT: {len(refs)} total, {len(valid)} valid, {len(ignored)} ignored")
    print(f"{'='*60}")

    print(f"\n--- Valid references (target paper) ---")
    for r in valid:
        order = r.get("reference_order", "?")
        title = str(r.get("title", ""))[:60]
        print(f"  #{order:>3}: {title}")

    if ignored:
        print(f"\n--- Ignored entries ({len(ignored)}) ---")
        for r in ignored:
            order = r.get("reference_order", "?")
            reason = r.get("ignore_reason", "")
            raw_preview = str(r.get("raw_text", ""))[:80]
            print(f"  #{order:>3} [{reason}]: {raw_preview}...")

    # Check numbering continuity
    orders = [r.get("reference_order", 0) for r in valid]
    gaps = []
    for i in range(len(orders)-1):
        if orders[i+1] - orders[i] > 1:
            gaps.append((orders[i], orders[i+1]))
    if gaps:
        print(f"\n  Numbering gaps: {gaps}")
    else:
        print(f"\n  Numbering: continuous from {min(orders)} to {max(orders)}")

    out_dir = Path("test_output")
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{stem}_complex_refs.json"
    out_file.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Saved: {out_file}")


if __name__ == "__main__":
    import sys
    pdf = sys.argv[1] if len(sys.argv) > 1 else "_uploads/yaojiaquan.pdf"
    run(pdf)
