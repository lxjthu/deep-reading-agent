"""Extract metadata-relevant text from the first 1-3 pages of a PDF or Markdown file."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber


def _is_markdown(file_path: str) -> bool:
    return file_path.lower().endswith((".md", ".markdown"))


DOI_PATTERN = re.compile(
    r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)

ISBN_10_PATTERN = re.compile(r"\b(\d{9}[\dXx])\b")
ISBN_13_PATTERN = re.compile(r"\b(978\d{10}|979\d{10})\b")


def extract_dois(text: str) -> list[str]:
    """Extract DOI candidates from text."""
    matches = DOI_PATTERN.findall(text)
    cleaned = []
    for doi in matches:
        doi = doi.rstrip(".,;:)")
        if doi:
            cleaned.append(doi.lower())
    return list(set(cleaned))


def extract_isbns(text: str) -> list[str]:
    """Extract ISBN candidates from text."""
    results = []
    for match in ISBN_13_PATTERN.finditer(text):
        results.append(match.group(1))
    for match in ISBN_10_PATTERN.finditer(text):
        results.append(match.group(1))
    return list(set(results))


def extract_page_header(page, max_lines: int = 8) -> str:
    """Extract header area (top portion) of a page."""
    text = page.extract_text() or ""
    if not text:
        return ""

    lines = text.splitlines()
    header_lines = []
    for line in lines[:max_lines * 2]:
        stripped = line.strip()
        if stripped:
            header_lines.append(stripped)
        if len(header_lines) >= max_lines:
            break

    return "\n".join(header_lines)


def _empty_front_matter() -> dict:
    return {
        "page_1_full": "",
        "page_2_header": "",
        "page_3_header": "",
        "doi_candidates": [],
        "isbn_candidates": [],
        "total_pages": 0,
    }


def extract_front_matter_md(md_path: str, max_lines: int = 150) -> dict:
    """Extract metadata-relevant text from a Markdown file.

    Reads the first ~max_lines and maps them into the same dict structure
    that extract_front_matter() returns for PDFs, so downstream consumers
    (extract_metadata_with_llm) work unchanged.
    """
    result = _empty_front_matter()

    if not Path(md_path).exists():
        return result

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line.rstrip("\n"))
    except Exception:
        return result

    full_text = "\n".join(lines)
    result["page_1_full"] = full_text

    chunk_size = max(max_lines // 3, 10)
    if len(lines) > chunk_size:
        result["page_2_header"] = "\n".join(lines[chunk_size : chunk_size * 2])
    if len(lines) > chunk_size * 2:
        result["page_3_header"] = "\n".join(lines[chunk_size * 2 : chunk_size * 3])

    result["doi_candidates"] = extract_dois(full_text)
    result["isbn_candidates"] = extract_isbns(full_text)
    result["total_pages"] = 1

    return result


def extract_front_matter(pdf_path: str, max_pages: int = 3) -> dict:
    """
    Extract metadata-relevant text from the first 1-3 pages of a PDF
    or the first ~150 lines of a Markdown file.

    Returns:
        dict with keys:
        - page_1_full: Full text of page 1 (or MD head)
        - page_2_header: Header + first few lines of page 2
        - page_3_header: Header + first few lines of page 3
        - doi_candidates: List of DOIs found in front matter
        - isbn_candidates: List of ISBNs found in front matter
        - total_pages: Total number of pages in PDF
    """
    if _is_markdown(pdf_path):
        return extract_front_matter_md(pdf_path)

    result = _empty_front_matter()

    if not Path(pdf_path).exists():
        return result

    with pdfplumber.open(pdf_path) as pdf:
        result["total_pages"] = len(pdf.pages)

        if len(pdf.pages) >= 1:
            page1 = pdf.pages[0]
            result["page_1_full"] = page1.extract_text() or ""

        if len(pdf.pages) >= 2:
            page2 = pdf.pages[1]
            result["page_2_header"] = extract_page_header(page2)

        if len(pdf.pages) >= 3:
            page3 = pdf.pages[2]
            result["page_3_header"] = extract_page_header(page3)

    combined_text = "\n".join([
        result["page_1_full"],
        result["page_2_header"],
        result["page_3_header"],
    ])

    result["doi_candidates"] = extract_dois(combined_text)
    result["isbn_candidates"] = extract_isbns(combined_text)

    return result
