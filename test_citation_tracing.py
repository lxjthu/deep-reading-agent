"""
Test DeepSeek citation tracing: link body sentences to reference entries.

Compares three approaches:
  1. Regex-only (current backend)
  2. Regex recall + DeepSeek verify (current citation_tracer.py style)
  3. DeepSeek direct (no regex pre-filter)

Usage:
    python test_citation_tracing.py path/to/paper.pdf
    python test_citation_tracing.py path/to/paper.pdf --refs-file path/to/deepseek_refs.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import json_repair
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

load_dotenv()

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"


def normalize_ws(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "")).strip()


REFERENCE_HEADINGS = {"references", "bibliography", "works cited", "参考文献"}


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
                            "paragraph_label": f"P{page_num}-{pid}",
                            "text": para,
                        })
            else:
                ref_lines.extend(lines)

    return paragraphs, "\n".join(ref_lines)


# ── Approach 1: Regex-only ────────────────────────────────────────
def build_regex_patterns(order: int, metadata: dict) -> list[tuple[str, str, float]]:
    patterns = []
    raw = metadata.get("raw_text", "")
    title = metadata.get("title") or ""
    authors = metadata.get("authors") or []
    year = metadata.get("year")

    numeric_match = re.match(r"^\s*(?:\[\s*(\d+)\s*\]|(\d{1,3})[.)、（])", raw)
    if numeric_match:
        num = numeric_match.group(1) or numeric_match.group(2)
        esc = re.escape(num)
        patterns.append((rf"[\[［(（]\s*{esc}\s*[\]］)）]", "numeric", 0.92))
        patterns.append((rf"\b{esc}\b", "numeric", 0.55))
    else:
        esc = re.escape(str(order))
        patterns.append((rf"[\[［(（]\s*{esc}\s*[\]］)）]", "numeric", 0.76))

    first_author = normalize_ws(authors[0]) if authors else ""
    if first_author and year:
        surname = re.split(r"[,，\s]", first_author, maxsplit=1)[0]
        surname = re.sub(r"[^\w\u4e00-\u9fff]+", "", surname)
        if surname:
            patterns.append((rf"{re.escape(surname)}.{{0,40}}{year}", "author_year", 0.88))
            patterns.append((rf"\({re.escape(surname)}.{{0,40}}{year}\)", "author_year", 0.9))

    title_kw = [w for w in re.split(r"[\s:：,，.;；()（）\-]+", title) if len(w) >= 4]
    if title_kw:
        phrase = re.escape(" ".join(title_kw[:4]))
        patterns.append((phrase, "title_keyword", 0.62))

    return patterns


def trace_regex(order: int, metadata: dict, paragraphs: list[dict]) -> list[dict]:
    citations = []
    seen = set()
    for pattern_str, method, confidence in build_regex_patterns(order, metadata):
        try:
            regex = re.compile(pattern_str, flags=re.IGNORECASE)
        except re.error:
            continue
        for para in paragraphs:
            for m in regex.finditer(para["text"]):
                key = (para["id"], m.start(), m.end())
                if key in seen:
                    continue
                seen.add(key)
                start = max(0, m.start() - 50)
                end = min(len(para["text"]), m.end() + 50)
                quote = para["text"][start:end].strip()
                citations.append({
                    "page_label": para["page_label"],
                    "quote_text": quote,
                    "match_method": method,
                    "confidence": confidence,
                })
                if len(citations) >= 8:
                    return citations
    return citations


# ── Approach 2: Regex recall + DeepSeek verify ────────────────────
def recall_candidates(order: int, metadata: dict, paragraphs: list[dict]) -> list[dict]:
    candidates = []
    seen_ids = set()
    for pattern_str, method, _ in build_regex_patterns(order, metadata):
        try:
            regex = re.compile(pattern_str, flags=re.IGNORECASE)
        except re.error:
            continue
        for para in paragraphs:
            if para["id"] in seen_ids:
                continue
            if regex.search(para["text"]):
                candidates.append(para)
                seen_ids.add(para["id"])
    return candidates[:12]


PROMPT_VERIFY = """You are verifying whether specific paragraphs actually cite a given reference.

## Reference
{ref_summary}

## Candidate paragraphs (might cite this reference)
{candidates_text}

## Task
1. Determine which paragraphs ACTUALLY cite this specific reference.
2. For each valid citation, extract the EXACT quote (1-2 sentences) that contains the citation.
3. Distinguish from same-name authors or unrelated mentions.
4. If a paragraph only lists citation numbers (e.g. "[1,2,3]"), still return the exact sentence containing the list.

## Output
Strict JSON:
```json
{{
  "citations": [
    {{
      "para_id": <int>,
      "quote": "exact quote from the paragraph",
      "confidence": 0.9
    }}
  ]
}}
```

If none of the paragraphs cite this reference, return: `{{"citations": []}}`"""


def trace_regex_llm(ref_summary: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []

    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    cand_text = "\n".join(f"[Para {c['id']}]: {c['text'][:1200]}" for c in candidates)
    user_msg = PROMPT_VERIFY.format(ref_summary=ref_summary, candidates_text=cand_text)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            extra_body={"thinking": {"type": "disabled"}},
            messages=[{"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        result = json_repair.repair_json(resp.choices[0].message.content, return_objects=True)
        items = result.get("citations", []) if isinstance(result, dict) else []
        para_map = {c["id"]: c for c in candidates}
        verified = []
        for item in items:
            if not isinstance(item, dict):
                continue
            pid = item.get("para_id")
            quote = (item.get("quote") or "").strip()
            if not quote:
                continue
            para = para_map.get(pid, {})
            verified.append({
                "page_label": para.get("page_label", ""),
                "quote_text": quote,
                "match_method": "regex+llm_verify",
                "confidence": item.get("confidence", 0.8),
            })
        return verified
    except Exception as e:
        print(f"    LLM verify error: {e}")
        return []


# ── Approach 3: DeepSeek direct (no regex) ───────────────────────
PROMPT_DIRECT = """You are an academic citation tracer. Your job is to find all sentences in the body text that cite a specific reference.

## Reference #{order}
Authors: {authors}
Year: {year}
Title: {title}

## Body text (truncated)
{body_text}

## Task
Find all sentences that cite or refer to this reference. Citations can appear as:
- Numeric: [1], [1,2], (1), etc.
- Author-year: Smith (2020), (Smith, 2020), Smith et al. (2020)
- Chinese style: 张三（2020）, 张三等（2020）
- Descriptive: "according to Smith's study on platform competition..."
- Title keywords from the reference

## Output
Strict JSON:
```json
{{
  "citations": [
    {{
      "quote": "the exact sentence or phrase that cites this reference",
      "citation_style": "numeric|author_year|descriptive",
      "confidence": 0.9
    }}
  ]
}}
```

If no citations found, return: `{{"citations": []}}`"""


def trace_llm_direct(order: int, metadata: dict, body_text: str) -> list[dict]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    authors = metadata.get("authors") or []
    body_chunk = body_text[:12000]

    user_msg = PROMPT_DIRECT.format(
        order=order,
        authors=", ".join(authors) if authors else "Unknown",
        year=metadata.get("year", "Unknown"),
        title=metadata.get("title") or "Unknown",
        body_text=body_chunk,
    )

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            extra_body={"thinking": {"type": "disabled"}},
            messages=[{"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        result = json_repair.repair_json(resp.choices[0].message.content, return_objects=True)
        items = result.get("citations", []) if isinstance(result, dict) else []
        return [
            {
                "quote_text": (item.get("quote") or "").strip(),
                "match_method": f"llm_direct:{item.get('citation_style', 'unknown')}",
                "confidence": item.get("confidence", 0.5),
            }
            for item in items
            if isinstance(item, dict) and (item.get("quote") or "").strip()
        ]
    except Exception as e:
        print(f"    LLM direct error: {e}")
        return []


# ── Run comparison ─────────────────────────────────────────────────
def run_test(pdf_path: str, refs_file: Optional[str] = None):
    print(f"Loading PDF: {pdf_path}")
    pages = extract_pdf_pages(pdf_path)
    paragraphs, ref_text = split_body_and_references(pages)
    print(f"  {len(pages)} pages, {len(paragraphs)} body paragraphs, {len(ref_text)} chars ref text")

    if refs_file and Path(refs_file).exists():
        refs = json.loads(Path(refs_file).read_text(encoding="utf-8"))
        print(f"  Loaded {len(refs)} refs from {refs_file}")
    else:
        print("  No refs file provided, run test_deepseek_references.py first")
        return

    valid_refs = [r for r in refs if not r.get("ignore")]
    body_text = "\n".join(p["text"] for p in paragraphs)
    print(f"  Body text: {len(body_text)} chars")

    results_regex = []
    results_regex_llm = []
    results_llm_direct = []

    total = len(valid_refs)
    test_limit = min(total, 10)
    print(f"\n  Testing first {test_limit} references (of {total} total)...\n")

    for i, ref in enumerate(valid_refs[:test_limit]):
        order = ref.get("reference_order", i + 1)
        title = ref.get("title") or "???"
        authors = ref.get("authors") or []
        year = ref.get("year")
        summary = f"#{order}: {', '.join(authors[:2])} ({year}) - {title}"
        print(f"  [{i+1}/{test_limit}] {summary[:80]}")

        # Approach 1: Regex only
        t0 = time.time()
        regex_hits = trace_regex(order, ref, paragraphs)
        dt1 = time.time() - t0
        results_regex.append(regex_hits)
        print(f"    Regex-only:   {len(regex_hits)} hits ({dt1:.2f}s)")

        # Approach 2: Regex recall + LLM verify
        t0 = time.time()
        candidates = recall_candidates(order, ref, paragraphs)
        if candidates:
            llm_hits = trace_regex_llm(summary, candidates)
        else:
            llm_hits = []
        dt2 = time.time() - t0
        results_regex_llm.append(llm_hits)
        print(f"    Regex+LLM:    {len(candidates)} candidates -> {len(llm_hits)} verified ({dt2:.1f}s)")

        # Approach 3: LLM direct
        t0 = time.time()
        direct_hits = trace_llm_direct(order, ref, body_text)
        dt3 = time.time() - t0
        results_llm_direct.append(direct_hits)
        print(f"    LLM-direct:   {len(direct_hits)} hits ({dt3:.1f}s)")

    # Summary
    total_regex = sum(len(r) for r in results_regex)
    total_regex_llm = sum(len(r) for r in results_regex_llm)
    total_direct = sum(len(r) for r in results_llm_direct)
    refs_with_regex = sum(1 for r in results_regex if r)
    refs_with_rllm = sum(1 for r in results_regex_llm if r)
    refs_with_direct = sum(1 for r in results_llm_direct if r)

    print(f"\n{'='*60}")
    print(f"  COMPARISON SUMMARY ({test_limit} references)")
    print(f"{'='*60}")
    print(f"  {'Approach':<20s} {'Total Hits':>12s} {'Refs with Hits':>15s}")
    print(f"  {'-'*50}")
    print(f"  {'Regex-only':<20s} {total_regex:>12d} {refs_with_regex:>15d}")
    print(f"  {'Regex+LLM verify':<20s} {total_regex_llm:>12d} {refs_with_rllm:>15d}")
    print(f"  {'LLM-direct':<20s} {total_direct:>12d} {refs_with_direct:>15d}")

    # Show examples
    print(f"\n{'='*60}")
    print(f"  SAMPLE QUOTES (Approach 2: Regex+LLM verify)")
    print(f"{'='*60}")
    shown = 0
    for i, (ref, hits) in enumerate(zip(valid_refs[:test_limit], results_regex_llm)):
        if hits:
            title = ref.get("title") or "???"
            print(f"\n  Ref #{ref.get('reference_order', i+1)}: {title[:60]}")
            for h in hits[:2]:
                print(f"    -> \"{h['quote_text'][:120]}\"")
            shown += 1
            if shown >= 5:
                break

    print(f"\n{'='*60}")
    print(f"  SAMPLE QUOTES (Approach 3: LLM-direct)")
    print(f"{'='*60}")
    shown = 0
    for i, (ref, hits) in enumerate(zip(valid_refs[:test_limit], results_llm_direct)):
        if hits:
            title = ref.get("title") or "???"
            print(f"\n  Ref #{ref.get('reference_order', i+1)}: {title[:60]}")
            for h in hits[:2]:
                print(f"    -> \"{h['quote_text'][:120]}\"")
            shown += 1
            if shown >= 5:
                break

    # Save results
    out_dir = SCRIPT_DIR / "test_output"
    out_dir.mkdir(exist_ok=True)
    stem = Path(pdf_path).stem
    out = {
        "pdf": pdf_path,
        "refs_tested": test_limit,
        "approaches": {
            "regex_only": {"total_hits": total_regex, "refs_with_hits": refs_with_regex},
            "regex_plus_llm": {"total_hits": total_regex_llm, "refs_with_hits": refs_with_rllm},
            "llm_direct": {"total_hits": total_direct, "refs_with_hits": refs_with_direct},
        },
        "details": [],
    }
    for i, ref in enumerate(valid_refs[:test_limit]):
        out["details"].append({
            "ref_order": ref.get("reference_order", i + 1),
            "title": ref.get("title"),
            "regex_hits": len(results_regex[i]),
            "regex_llm_hits": len(results_regex_llm[i]),
            "llm_direct_hits": len(results_llm_direct[i]),
            "regex_llm_quotes": [h["quote_text"] for h in results_regex_llm[i][:3]],
            "llm_direct_quotes": [h["quote_text"] for h in results_llm_direct[i][:3]],
        })
    out_file = out_dir / f"{stem}_citation_comparison.json"
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Detailed results: {out_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", help="PDF file path")
    parser.add_argument("--refs-file", help="JSON file from test_deepseek_references.py")
    args = parser.parse_args()
    run_test(args.pdf_path, args.refs_file)
