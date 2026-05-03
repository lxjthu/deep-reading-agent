"""Extract metadata-relevant text from the first 1-3 pages of a PDF."""
from __future__ import annotations

import re
from pathlib import Path

import pdfplumber


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


def extract_front_matter(pdf_path: str, max_pages: int = 3) -> dict:
    """
    Extract metadata-relevant text from the first 1-3 pages of a PDF.

    Returns:
        dict with keys:
        - page_1_full: Full text of page 1
        - page_2_header: Header + first few lines of page 2
        - page_3_header: Header + first few lines of page 3
        - doi_candidates: List of DOIs found in front matter
        - isbn_candidates: List of ISBNs found in front matter
        - total_pages: Total number of pages in PDF
    """
    result = {
        "page_1_full": "",
        "page_2_header": "",
        "page_3_header": "",
        "doi_candidates": [],
        "isbn_candidates": [],
        "total_pages": 0,
    }

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
