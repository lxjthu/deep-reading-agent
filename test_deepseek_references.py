"""
Test DeepSeek v4-flash reference recognition capability.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

import json_repair
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

load_dotenv()

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── Config ──────────────────────────────────────────────────────────
MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
CHUNK_SIZE = 8000
REFERENCE_HEADINGS = {"references", "bibliography", "works cited", "参考文献"}


# ── PDF Text Extraction ────────────────────────────────────────────
def extract_pdf_pages(file_path: str) -> list[str]:
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if normalize_ws(text):
            pages.append(text)
    return pages


def normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def is_reference_heading(line: str) -> bool:
    stripped = normalize_ws(line).strip(":：").lower()
    if stripped in REFERENCE_HEADINGS:
        return True
    return bool(re.match(r"^\d+(\.\d+)*\s*(references|bibliography|works cited|参考文献)$", stripped))


# ── Stage A: Locate candidate reference section ────────────────────
def locate_reference_candidate(pages: list[str]) -> tuple[str, str]:
    """Return (body_text, reference_candidate_text)."""
    ref_lines = []
    body_paragraphs = []
    in_references = False

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
                        ref_lines.extend(lines[i + 1:])
                        break
                if not in_references:
                    para = normalize_ws(" ".join(lines))
                    if len(para) >= 40:
                        body_paragraphs.append(para)
            else:
                ref_lines.extend(lines)

    return "\n".join(body_paragraphs), "\n".join(ref_lines)


# ── Stage B+C: DeepSeek parsing ────────────────────────────────────
def get_client() -> OpenAI:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置，请检查 .env 文件")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


PROMPT_STAGE_BC = """你是一个学术文献参考文献解析专家。

## 输入
你看到的是一篇学术论文 PDF 尾部提取的原始文本。该文本可能包含：
1. 真正的参考文献条目（最常见）
2. 文末可能出现的英文摘要（Abstract）、附录（Appendix）、补充材料（Supplementary Material）、致谢（Acknowledgements）、作者简介（Author Biography）等非参考文献内容

## 任务
1. 识别出文本中**真正的参考文献条目**，合并被 PDF 提取器错误断行的内容
2. 忽略所有非参考文献内容（摘要、附录、补充材料、致谢、作者简介等）
3. 对每条参考文献提取结构化字段
4. 不确定的字段填 null，不要编造

## 输出格式
严格输出 JSON：
```json
{
  "references": [
    {
      "reference_order": 1,
      "raw_text": "该条目的完整原文（合并断行后）",
      "authors": ["作者1", "作者2"],
      "year": 2020,
      "title": "论文/书籍标题",
      "journal": "期刊/出版社名",
      "volume": "卷号",
      "issue": "期号",
      "pages": "页码范围",
      "doi": "DOI（如有）",
      "language": "en 或 zh",
      "ignore": false,
      "ignore_reason": null
    }
  ]
}
```

## 关键约束
- `references` 必须是数组
- `reference_order` 按原文顺序编号
- 如果某段文本不是参考文献（如摘要段落、附录标题），设置 `"ignore": true` 并在 `ignore_reason` 说明
- `authors` 是数组，不确定则 `null`
- 年份必须是整数，不确定则 `null`
- DOI 格式：`10.xxxx/...`，不确定则 `null`
- 不得编造任何字段
- 保留每条的完整 `raw_text`"""


def call_deepseek_references(client: OpenAI, chunk_text: str, chunk_label: str = "") -> list[dict]:
    user_content = f"## 候选参考文献文本\n\n{chunk_text}"
    try:
        t0 = time.time()
        response = client.chat.completions.create(
            model=MODEL,
            extra_body={"thinking": {"type": "disabled"}},
            messages=[
                {"role": "system", "content": PROMPT_STAGE_BC},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        elapsed = time.time() - t0
        usage = response.usage
        raw = response.choices[0].message.content
        result = json_repair.repair_json(raw, return_objects=True)

        if isinstance(result, dict):
            refs = result.get("references", [])
        elif isinstance(result, list):
            refs = result
        else:
            refs = []

        cache_info = ""
        if usage:
            prompt_tokens = usage.prompt_tokens or 0
            completion_tokens = usage.completion_tokens or 0
            cache_hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
            cache_info = f"prompt={prompt_tokens}, completion={completion_tokens}, cache_hit={cache_hit}"

        print(f"  [{chunk_label}] 提取 {len(refs)} 条 | {elapsed:.1f}s | {cache_info}")
        return refs

    except Exception as e:
        print(f"  [{chunk_label}] ❌ 调用失败: {e}")
        return []


def parse_with_deepseek(ref_text: str) -> list[dict]:
    if len(ref_text.strip()) < 50:
        print("  候选文本太短，跳过")
        return []

    client = get_client()
    all_refs = []
    total = len(ref_text)

    for start in range(0, total, CHUNK_SIZE):
        chunk = ref_text[start:start + CHUNK_SIZE]
        if start > 0:
            nl = chunk.find('\n')
            if 0 < nl < 200:
                chunk = chunk[nl + 1:]
        if start + CHUNK_SIZE < total:
            last_nl = chunk.rfind('\n')
            if last_nl > len(chunk) - 200:
                chunk = chunk[:last_nl]
        if len(chunk.strip()) < 30:
            continue
        label = f"{start}-{start + len(chunk)}"
        refs = call_deepseek_references(client, chunk, label)
        all_refs.extend(refs)

    return all_refs


# ── Stage D: Validation & normalization ────────────────────────────
def validate_single_ref(ref: dict, index: int) -> dict:
    errors = []
    if not ref.get("raw_text"):
        errors.append("缺少 raw_text")
    if not isinstance(ref.get("reference_order"), int):
        ref["reference_order"] = index
    authors = ref.get("authors")
    if authors is not None and not isinstance(authors, list):
        ref["authors"] = None
        errors.append(f"authors 不是数组: {type(authors)}")
    year = ref.get("year")
    if year is not None:
        try:
            ref["year"] = int(year)
        except (ValueError, TypeError):
            ref["year"] = None
            errors.append(f"year 无法转整数: {year}")
    doi = ref.get("doi")
    if doi:
        match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", str(doi), flags=re.IGNORECASE)
        ref["doi"] = match.group(1).rstrip(".,;)").lower() if match else None
        if not ref["doi"]:
            errors.append(f"DOI 格式异常: {doi}")
    lang = ref.get("language")
    if lang not in ("en", "zh", None):
        ref["language"] = "en" if re.search(r"[a-zA-Z]", ref.get("raw_text", "")) else "zh"

    ref["_validation_errors"] = errors
    return ref


def validate_all_refs(refs: list[dict]) -> dict:
    report = {"total": len(refs), "ignored": 0, "valid": 0, "field_stats": {}, "errors": []}
    field_names = ["authors", "year", "title", "journal", "doi", "volume", "issue", "pages", "language"]
    field_present = {f: 0 for f in field_names}

    for i, ref in enumerate(refs):
        ref = validate_single_ref(ref, i + 1)
        if ref.get("ignore"):
            report["ignored"] += 1
            continue
        report["valid"] += 1
        for f in field_names:
            if ref.get(f) is not None:
                field_present[f] += 1
        if ref.get("_validation_errors"):
            report["errors"].append({"order": ref.get("reference_order", i + 1), "errors": ref["_validation_errors"]})
            del ref["_validation_errors"]

    report["field_stats"] = field_present
    return report


# ── Old regex-based extraction (for comparison) ───────────────────
def old_regex_split(ref_text: str) -> list[str]:
    lines = [normalize_ws(l) for l in ref_text.splitlines() if normalize_ws(l)]
    lines = [l for l in lines if not l.startswith("Page ") and not re.fullmatch(r"\d+", l)]

    entries = []
    current = []
    for line in lines:
        is_boundary = bool(re.match(r"^(?:\[\d+\]|\d{1,3}[.)、])\s*", line))
        if not is_boundary and current:
            joined = " ".join(current)
            if len(joined) >= 60:
                if re.match(r"^[A-Z][A-Za-z'`\-]+(?:,\s*[A-Z][A-Za-z'`\-.\s]+){0,5}", line):
                    is_boundary = True
                if re.match(r"^[\u4e00-\u9fff]{1,6}[,，、\s].{0,40}(19|20)\d{2}", line):
                    is_boundary = True
        if is_boundary and current:
            entries.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        entries.append(" ".join(current).strip())
    if len(entries) <= 1:
        chunks = re.split(r"(?m)(?=^(?:\[\d+\]|\d{1,3}[.)、])\s*)", "\n".join(lines))
        fallback = [normalize_ws(c) for c in chunks if normalize_ws(c)]
        if len(fallback) > len(entries):
            entries = fallback
    return [e for e in entries if len(e) >= 20]


def old_regex_parse_metadata(raw_text: str) -> dict:
    text = normalize_ws(raw_text)
    doi = None
    m = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, flags=re.IGNORECASE)
    if m:
        doi = m.group(1).rstrip(".,;)").lower()
    year_match = re.search(r"(19|20)\d{2}[a-z]?", text, flags=re.IGNORECASE)
    year = int(re.search(r"(19|20)\d{2}", year_match.group(0)).group(0)) if year_match else None
    authors = []
    if year_match:
        author_text = text[:year_match.start()]
        author_text = re.sub(r"^\s*(?:\[\d+\]|\d{1,3}[.)、])\s*", "", author_text).strip(" .;:")
        if author_text:
            if re.search(r"[\u4e00-\u9fff]", author_text):
                parts = re.split(r"[、，,;；]+", author_text)
            else:
                author_text = author_text.replace(" & ", ", ").replace(" and ", ", ")
                parts = re.split(r";|,(?=\s*[A-Z])", author_text)
            authors = [normalize_ws(p).strip(".,") for p in parts if normalize_ws(p).strip(".,")][:8]
    title = None
    after_year = text
    if year_match:
        after_year = text[year_match.end():].lstrip(").].,:; ")
    title_match = re.search(r'[\u201c"\u201c]([^\u201d"]+)[\u201d"]', after_year)
    if title_match:
        title = normalize_ws(title_match.group(1))
    elif "[J]" in after_year:
        title = normalize_ws(after_year.split("[J]", 1)[0].strip(" .;:"))
    else:
        title = normalize_ws(re.split(r"\.\s+", after_year, maxsplit=1)[0].strip(" .;:"))
    if title and len(title) < 4:
        title = None
    journal = None
    if title and title in after_year:
        remaining = after_year.split(title, 1)[1].lstrip(" .;:[]")
        journal = normalize_ws(re.split(r"\.\s+|\s+\d{4}\b", remaining, maxsplit=1)[0].strip(" .;:"))
    vol_match = re.search(r"(\d+)\s*\(([^)]+)\)", text)
    pages_match = re.search(r"(\d+\s*[-–]\s*\d+)", text)
    language = "zh" if re.search(r"[\u4e00-\u9fff]", text) else "en"
    return {
        "raw_text": text, "authors": authors, "year": year, "title": title,
        "journal": journal, "doi": doi, "language": language,
        "volume": vol_match.group(1) if vol_match else None,
        "issue": vol_match.group(2).strip() if vol_match else None,
        "pages": pages_match.group(1).replace(" ", "") if pages_match else None,
    }


# ── DB write test ──────────────────────────────────────────────────
def test_db_write(refs: list[dict], source_bib_entry_id: str, user_id: int = 1) -> bool:
    try:
        import asyncio
        from db import AsyncSessionLocal
        from db.models import BibReference
        from db.utils import compute_dedup_key

        test_task_id = f"test-{uuid.uuid4()}"
        test_refs = []
        for i, ref in enumerate(refs):
            if ref.get("ignore"):
                continue
            authors = ref.get("authors")
            if isinstance(authors, str):
                authors = [authors]
            dedup = compute_dedup_key(
                ref.get("doi"),
                ref.get("title") or ref.get("raw_text", "")[:80],
                authors,
                ref.get("year"),
            )
            test_refs.append(BibReference(
                id=str(uuid.uuid4()),
                owner_user_id=user_id,
                source_bib_entry_id=source_bib_entry_id,
                source_job_id=None,
                reference_order=ref.get("reference_order", i + 1),
                raw_text=ref.get("raw_text", ""),
                authors_json=json.dumps(authors or [], ensure_ascii=False),
                year=ref.get("year"),
                title=ref.get("title"),
                journal=ref.get("journal"),
                volume=ref.get("volume"),
                issue=ref.get("issue"),
                pages=ref.get("pages"),
                doi=ref.get("doi"),
                language=ref.get("language"),
                dedup_key=dedup,
                citation_count=0,
                updated_at=datetime.now(UTC).replace(tzinfo=None),
            ))

        async def _write():
            async with AsyncSessionLocal() as db:
                for r in test_refs[:3]:
                    db.add(r)
                await db.flush()
                await db.rollback()
                return True

        result = asyncio.run(_write())
        return True
    except Exception as e:
        print(f"\n  ❌ 数据库写入测试失败: {e}")
        return False


# ── Report ─────────────────────────────────────────────────────────
def print_report(pdf_name: str, refs: list[dict], report: dict):
    print(f"\n{'='*60}")
    print(f"PDF: {pdf_name}")
    print(f"{'='*60}")
    print(f"  总条目数:        {report['total']}")
    print(f"  有效参考文献:    {report['valid']}")
    print(f"  标记忽略:        {report['ignored']}")
    print(f"\n  字段覆盖率:")
    valid = report["valid"] or 1
    for field, count in report["field_stats"].items():
        pct = count / valid * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {field:12s} {bar} {count}/{valid} ({pct:.0f}%)")
    if report["errors"]:
        print(f"\n  ⚠ 验证问题 ({len(report['errors'])} 条):")
        for err in report["errors"][:5]:
            print(f"    #{err['order']}: {'; '.join(err['errors'])}")
    ignored_refs = [r for r in refs if r.get("ignore")]
    if ignored_refs:
        print(f"\n  被忽略的内容 ({len(ignored_refs)} 条):")
        for ref in ignored_refs[:5]:
            reason = ref.get("ignore_reason", "未说明原因")
            text_preview = (ref.get("raw_text") or "")[:80]
            print(f"    #{ref.get('reference_order', '?')}: [{reason}] {text_preview}...")


def print_comparison(refs_deepseek: list[dict], refs_regex_raw: list[str]):
    ds_valid = [r for r in refs_deepseek if not r.get("ignore")]
    print(f"\n{'='*60}")
    print(f"  对比：DeepSeek vs 旧规则")
    print(f"{'='*60}")
    print(f"  DeepSeek 有效条目数:  {len(ds_valid)}")
    print(f"  旧规则拆分条目数:    {len(refs_regex_raw)}")

    ds_titles = set()
    for r in ds_valid:
        t = r.get("title")
        if t:
            ds_titles.add(re.sub(r"[^\w]+", "", t.lower())[:40])

    regex_titles = set()
    for raw in refs_regex_raw:
        parsed = old_regex_parse_metadata(raw)
        t = parsed.get("title")
        if t:
            regex_titles.add(re.sub(r"[^\w]+", "", t.lower())[:40])

    ds_only = ds_titles - regex_titles
    regex_only = regex_titles - ds_titles
    both = ds_titles & regex_titles
    print(f"\n  标题匹配:")
    print(f"    双方都识别:    {len(both)}")
    print(f"    仅 DeepSeek:   {len(ds_only)}")
    print(f"    仅旧规则:      {len(regex_only)}")

    if ds_only:
        print(f"\n  仅 DeepSeek 识别到的标题（前5条）:")
        for t in list(ds_only)[:5]:
            print(f"    - {t}")
    if regex_only:
        print(f"\n  仅旧规则识别到的标题（前5条）:")
        for t in list(regex_only)[:5]:
            print(f"    - {t}")

    ds_with_title = sum(1 for r in ds_valid if r.get("title"))
    regex_with_title = 0
    for raw in refs_regex_raw:
        parsed = old_regex_parse_metadata(raw)
        if parsed.get("title"):
            regex_with_title += 1
    print(f"\n  标题识别率:")
    print(f"    DeepSeek:  {ds_with_title}/{len(ds_valid)} ({ds_with_title / max(len(ds_valid), 1) * 100:.0f}%)")
    print(f"    旧规则:    {regex_with_title}/{len(refs_regex_raw)} ({regex_with_title / max(len(refs_regex_raw), 1) * 100:.0f}%)")


# ── Main ───────────────────────────────────────────────────────────
def find_pdfs() -> list[Path]:
    upload_dir = SCRIPT_DIR / "_uploads" / "1"
    if upload_dir.exists():
        pdfs = list(upload_dir.glob("*.pdf"))
        if pdfs:
            return pdfs
    upload_root = SCRIPT_DIR / "_uploads"
    return list(upload_root.rglob("*.pdf")) if upload_root.exists() else []


def process_pdf(pdf_path: Path, do_compare: bool = False, do_db: bool = False):
    print(f"\n{'#'*60}")
    print(f"# 处理: {pdf_path.name}")
    print(f"# 大小: {pdf_path.stat().st_size / 1024:.0f} KB")
    print(f"{'#'*60}")

    print("\n[1/3] 提取 PDF 文本...")
    pages = extract_pdf_pages(str(pdf_path))
    print(f"  共 {len(pages)} 页")

    print("\n[2/3] 定位参考文献候选区...")
    body_text, ref_text = locate_reference_candidate(pages)
    print(f"  正文长度: {len(body_text)} 字符")
    print(f"  参考文献候选区长度: {len(ref_text)} 字符")
    if len(ref_text) < 50:
        print("  ⚠ 候选区太短，可能未找到参考文献区")
        if len(pages) >= 2:
            print("  尝试取最后 3 页作为候选区...")
            tail_pages = pages[-3:]
            ref_text = "\n".join(tail_pages)
            print(f"  尾部候选区长度: {len(ref_text)} 字符")

    print(f"\n  候选区预览（前300字）:")
    print(f"  {'-'*50}")
    for line in ref_text[:300].split("\n"):
        print(f"  {line}")
    print(f"  {'-'*50}")

    print("\n[3/3] DeepSeek 解析参考文献...")
    refs = parse_with_deepseek(ref_text)
    if not refs:
        print("  ❌ 未提取到任何参考文献")
        return

    report = validate_all_refs(refs)
    print_report(pdf_path.name, refs, report)

    if do_compare:
        print("\n[对比] 运行旧规则拆分...")
        regex_entries = old_regex_split(ref_text)
        regex_parsed = [old_regex_parse_metadata(e) for e in regex_entries]
        print_comparison(refs, regex_entries)

    if do_db:
        print("\n[数据库] 测试写入...")
        source_id = str(uuid.uuid4())
        ok = test_db_write(refs, source_id)
        if ok:
            print("  ✅ 数据库写入+回滚测试通过（未实际写入数据）")

    output_dir = SCRIPT_DIR / "test_output"
    output_dir.mkdir(exist_ok=True)
    out_file = output_dir / f"{pdf_path.stem}_deepseek_refs.json"
    out_file.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  详细结果已保存: {out_file}")

    return refs, report


def main():
    parser = argparse.ArgumentParser(description="测试 DeepSeek 识别参考文献能力")
    parser.add_argument("pdf_path", nargs="?", help="PDF 文件路径（默认自动查找）")
    parser.add_argument("--db-test", action="store_true", help="测试数据库写入")
    parser.add_argument("--compare", action="store_true", help="对比旧规则 vs DeepSeek")
    args = parser.parse_args()

    if args.pdf_path:
        pdfs = [Path(args.pdf_path)]
    else:
        pdfs = find_pdfs()

    if not pdfs:
        print("未找到可测试的 PDF 文件")
        print("用法: python test_deepseek_references.py path/to/paper.pdf")
        sys.exit(1)

    print(f"找到 {len(pdfs)} 个 PDF 文件")
    all_results = {}
    for pdf in pdfs:
        result = process_pdf(pdf, do_compare=args.compare, do_db=args.db_test)
        if result:
            all_results[pdf.name] = {"refs": len(result[0]), "valid": result[1]["valid"]}

    print(f"\n{'='*60}")
    print("总结")
    print(f"{'='*60}")
    for name, info in all_results.items():
        print(f"  {name}: {info['valid']} 有效参考文献 / {info['refs']} 总条目")


if __name__ == "__main__":
    main()
