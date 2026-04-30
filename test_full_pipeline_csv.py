"""
Run full pipeline (reference extraction + citation tracing) on a single PDF,
output a CSV for human review.

Usage:
    python test_full_pipeline_csv.py path/to/paper.pdf
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
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
CHUNK_SIZE = 12000

REFERENCE_HEADINGS = {"references", "bibliography", "works cited", "参考文献"}


def normalize_ws(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "")).strip()


def is_reference_heading(line: str) -> bool:
    stripped = normalize_ws(line).strip(":：").lower()
    if stripped in REFERENCE_HEADINGS:
        return True
    return bool(re.match(r"^\d+(\.\d+)*\s*(references|bibliography|works cited|参考文献)$", stripped))


def extract_pdf_pages(file_path: str) -> list[str]:
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if normalize_ws(text):
            pages.append(text)
    return pages


def split_body_and_references(pages: list[str]) -> tuple[list[dict], str]:
    paragraphs = []
    ref_lines = []
    in_references = False
    pid = 0
    for page_num, page_text in enumerate(pages, 1):
        blocks = re.split(r"\n\s*\n", page_text)
        if len(blocks) == 1:
            blocks = page_text.splitlines()
        for block in blocks:
            lines = [normalize_ws(l) for l in block.splitlines() if normalize_ws(l)]
            if not lines:
                continue
            if not in_references:
                for i, line in enumerate(lines):
                    if is_reference_heading(line):
                        in_references = True
                        ref_lines.extend(lines[i + 1 :])
                        break
                if not in_references:
                    para = normalize_ws(" ".join(lines))
                    if len(para) >= 40:
                        pid += 1
                        paragraphs.append({
                            "id": pid,
                            "page_label": f"P{page_num}",
                            "text": para,
                        })
            else:
                ref_lines.extend(lines)
    return paragraphs, "\n".join(ref_lines)


PROMPT_EXTRACT = """You are an expert academic reference parser.

## Input
You see raw text extracted from the end of an academic PDF. It may contain:
1. Actual reference entries
2. Non-reference content: abstracts, appendices, supplementary material, acknowledgements, author bios

## Task
1. Identify each actual reference entry, merging broken lines
2. Ignore all non-reference content
3. Extract structured fields for each entry
4. Return null for uncertain fields - never fabricate

## Output
Strict JSON:
```json
{
  "references": [
    {
      "reference_order": 1,
      "raw_text": "complete original text of this entry",
      "authors": ["Author1", "Author2"],
      "year": 2020,
      "title": "Paper Title",
      "journal": "Journal Name",
      "volume": "10",
      "issue": "2",
      "pages": "1-20",
      "doi": "10.xxxx/...",
      "language": "en",
      "ignore": false,
      "ignore_reason": null
    }
  ]
}
```

## Constraints
- `references` must be an array
- `reference_order` follows original order
- If content is not a reference, set `ignore: true` with `ignore_reason`
- `authors` must be array or null
- `year` must be integer or null
- DOI format: `10.xxxx/...` or null
- Never fabricate any field
- Preserve full `raw_text` for each entry
- Prompt contains JSON example as required by API"""


PROMPT_CITE = """You are an academic citation tracer. Find ALL sentences in the body text that cite or refer to specific references.

## Reference List
{ref_list}

## Body Text
{body_text}

## Task
For EACH reference above, find all sentences in the body text that cite it. Citations can appear as:
- Numeric: [1], [1,2], (1), ①, etc.
- Author-year: Smith (2020), (Smith, 2020), Smith et al. (2020)
- Chinese: 张三（2020）, 张三等（2020）
- Descriptive: "according to Smith's study on...", "following the approach in [1]..."
- Indirect: paraphrased descriptions that clearly refer to a specific reference

## Output
Strict JSON:
```json
{
  "citation_traces": [
    {
      "reference_order": 1,
      "citations": [
        {
          "quote": "exact sentence from body text",
          "citation_style": "numeric|author_year|descriptive|indirect",
          "confidence": 0.9
        }
      ]
    }
  ]
}
```

## Constraints
- `quote` must be an exact substring from the body text
- If a reference is not cited, return empty citations array
- Do NOT fabricate quotes
- Prefer precision over recall - if unsure, omit
- Must output JSON"""


def call_deepseek(client, messages, label="", max_retries=3):
    for attempt in range(max_retries):
        try:
            t0 = time.time()
            resp = client.chat.completions.create(
                model=MODEL,
                extra_body={"thinking": {"type": "disabled"}},
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            elapsed = time.time() - t0
            raw = resp.choices[0].message.content
            if not raw or not raw.strip():
                print(f"    [{label}] Empty content (attempt {attempt+1}/{max_retries})")
                continue
            usage = resp.usage
            cache_hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
            print(f"    [{label}] {elapsed:.1f}s, cache_hit={cache_hit}, chars={len(raw)}")
            result = json_repair.repair_json(raw, return_objects=True)
            return result
        except Exception as e:
            print(f"    [{label}] Error (attempt {attempt+1}): {e}")
    print(f"    [{label}] All {max_retries} retries failed")
    return None


def extract_references(client, ref_text: str) -> list[dict]:
    if len(ref_text.strip()) < 50:
        return []

    all_refs = []
    total = len(ref_text)

    for start in range(0, total, CHUNK_SIZE):
        chunk = ref_text[start : start + CHUNK_SIZE]
        if start > 0:
            nl = chunk.find("\n")
            if 0 < nl < 200:
                chunk = chunk[nl + 1 :]
        if start + CHUNK_SIZE < total:
            last_nl = chunk.rfind("\n")
            if last_nl > len(chunk) - 200:
                chunk = chunk[:last_nl]
        if len(chunk.strip()) < 30:
            continue

        label = f"ref-{start}-{start+len(chunk)}"
        messages = [
            {"role": "system", "content": PROMPT_EXTRACT},
            {"role": "user", "content": f"## Candidate reference text\n\n{chunk}"},
        ]
        result = call_deepseek(client, messages, label=label)
        if result:
            refs = result.get("references", []) if isinstance(result, dict) else []
            all_refs.extend(refs)

    return all_refs


def trace_citations(client, refs: list[dict], body_text: str) -> dict[int, list[dict]]:
    ref_list_parts = []
    for r in refs:
        if r.get("ignore"):
            continue
        authors = ", ".join(r.get("authors", [])[:3])
        ref_list_parts.append(
            f"  [{r.get('reference_order', 0)}] {authors} ({r.get('year', '?')}) - {r.get('title', '???')}"
        )
    ref_list = "\n".join(ref_list_parts)

    body_for_prompt = body_text[:80000]

    system_content = PROMPT_CITE.replace("{ref_list}", ref_list).replace("{body_text}", body_for_prompt)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "Please trace all citations now."},
    ]
    result = call_deepseek(client, messages, label="citation-trace")
    if not result:
        return {}

    traces = result.get("citation_traces", []) if isinstance(result, dict) else []
    trace_map = {}
    for t in traces:
        order = t.get("reference_order", 0)
        trace_map[order] = t.get("citations", [])
    return trace_map


def run(pdf_path: str):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    stem = Path(pdf_path).stem
    print(f"=== Full Pipeline: {stem} ===\n")

    # Step 1: PDF text
    print("[1/4] Extracting PDF text...")
    pages = extract_pdf_pages(pdf_path)
    paragraphs, ref_text = split_body_and_references(pages)
    body_text = "\n".join(p["text"] for p in paragraphs)
    print(f"  {len(pages)} pages, {len(paragraphs)} paragraphs, body={len(body_text)} chars, refs={len(ref_text)} chars\n")

    # Step 2: Extract references
    print("[2/4] Extracting references with DeepSeek...")
    refs = extract_references(client, ref_text)
    valid_refs = [r for r in refs if not r.get("ignore")]
    print(f"  {len(valid_refs)} valid references extracted\n")

    if not valid_refs:
        print("No references found, aborting.")
        return

    # Re-number sequentially (PDF may have gaps like 31 -> 99)
    old_to_new = {}
    for i, r in enumerate(valid_refs, 1):
        old_order = r.get("reference_order", i)
        old_to_new[old_order] = i
        r["reference_order"] = i

    # Step 3: Trace citations
    print("[3/4] Tracing citations with DeepSeek...")
    trace_map = trace_citations(client, valid_refs, body_text)
    traced_count = sum(1 for r in valid_refs if trace_map.get(r.get("reference_order", 0)))
    total_citations = sum(len(v) for v in trace_map.values())
    print(f"  {traced_count}/{len(valid_refs)} refs have citations, {total_citations} total citation hits\n")

    # Step 4: Generate CSV
    print("[4/4] Generating CSV...")
    out_dir = Path("test_output")
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"{stem}_full_result.csv"

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "序号", "作者", "年份", "标题", "期刊", "DOI",
            "引用次数", "引用方式", "引用原文1", "引用原文2", "引用原文3",
            "raw_text",
        ])
        for ref in valid_refs:
            order = ref.get("reference_order", 0)
            authors = ", ".join(ref.get("authors", []))
            year = ref.get("year", "")
            title = ref.get("title", "")
            journal = ref.get("journal", "")
            doi = ref.get("doi", "")
            raw = ref.get("raw_text", "")

            citations = trace_map.get(order, [])
            cite_count = len(citations)
            styles = list(set(c.get("citation_style", "") for c in citations)) if citations else []
            style_str = ", ".join(styles)

            quotes = [c.get("quote", "") for c in citations[:3]]
            while len(quotes) < 3:
                quotes.append("")

            writer.writerow([
                order, authors, year, title, journal, doi,
                cite_count, style_str,
                quotes[0], quotes[1], quotes[2],
                raw,
            ])

    print(f"  CSV saved: {csv_path}\n")
    print(f"{'='*60}")
    print(f"RESULT: {len(valid_refs)} refs, {total_citations} citations")
    print(f"{'='*60}")

    # Also save JSON
    json_path = out_dir / f"{stem}_full_result.json"
    json_path.write_text(
        json.dumps({"references": valid_refs, "citation_traces": {str(k): v for k, v in trace_map.items()}},
                    ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  JSON saved: {json_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    args = parser.parse_args()
    run(args.pdf_path)
