"""Use DeepSeek to extract structured metadata from PDF front matter."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import json_repair
from openai import OpenAI
from backend.utils.api_key import validate_deepseek_key

logger = logging.getLogger(__name__)

MODEL = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
MAX_RETRIES = 3

PROMPT = """You are an academic paper metadata extraction expert.

## Task
Extract structured metadata from the following text extracted from the first 1-3 pages of a PDF.

## Input
- Filename: {filename}
- Page 1 text:
{page_1}

- Page 2 header:
{page_2}

- Page 3 header:
{page_3}

- DOIs found by regex: {dois}

## Output Format
Strict JSON:
```json
{{
  "title": "Paper title",
  "authors": ["Author 1", "Author 2"],
  "year": 2024,
  "journal": "Journal Name",
  "doi": "10.1234/example",
  "volume": "12",
  "issue": "3",
  "pages": "1-20",
  "abstract": "Paper abstract text...",
  "keywords": ["keyword1", "keyword2"],
  "language": "en",
  "confidence": 0.85
}}
```

## Rules
- If a field cannot be determined, use null (not empty string)
- Do NOT fabricate information
- confidence: 0.0-1.0, how confident you are in the extraction
- language: "zh" for Chinese, "en" for English
- abstract: extract the full abstract from the first page; if not found, use null
- keywords: extract keywords (usually after the abstract, separated by semicolons or commas); return as a list
- If regex found DOIs, include them in your output"""


def extract_metadata_with_llm(
    front_matter: dict,
    filename: str,
    api_key: Optional[str] = None,
) -> dict:
    """
    Call DeepSeek to extract structured metadata from PDF front matter.

    Args:
        front_matter: Dict from extract_front_matter()
        filename: Original PDF filename
        api_key: Optional DeepSeek API key

    Returns:
        Dict with title, authors, year, journal, doi, volume, issue, pages, language, confidence
    """
    api_key = validate_deepseek_key(api_key)
    client = OpenAI(api_key=api_key, base_url=BASE_URL)

    prompt = PROMPT.format(
        filename=filename,
        page_1=front_matter.get("page_1_full", "")[:3000],
        page_2=front_matter.get("page_2_header", "")[:1000],
        page_3=front_matter.get("page_3_header", "")[:1000],
        dois=", ".join(front_matter.get("doi_candidates", [])) or "none found",
    )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Extract metadata from the provided text."},
    ]

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                extra_body={"thinking": {"type": "disabled"}},
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2048,
            )
            raw = resp.choices[0].message.content
            if raw and raw.strip():
                result = json_repair.repair_json(raw, return_objects=True)
                if isinstance(result, dict):
                    return _clean_metadata(result)
        except Exception as e:
            logger.warning("DeepSeek metadata extraction attempt %d failed: %s", attempt + 1, e)

    return _empty_metadata()


def _clean_metadata(data: dict) -> dict:
    """Clean and validate metadata fields."""
    result = _empty_metadata()

    # Title
    title = data.get("title")
    if title and isinstance(title, str) and len(title.strip()) >= 3:
        result["title"] = title.strip()

    # Authors
    authors = data.get("authors")
    if authors and isinstance(authors, list):
        result["authors"] = [str(a).strip() for a in authors if str(a).strip()]

    # Year
    year = data.get("year")
    if year:
        try:
            year_int = int(year)
            if 1900 <= year_int <= 2030:
                result["year"] = year_int
        except (ValueError, TypeError):
            pass

    # String fields
    for field in ["journal", "doi", "volume", "issue", "pages", "abstract"]:
        value = data.get(field)
        if value and isinstance(value, str) and value.strip() and value.strip().lower() != "null":
            result[field] = value.strip()

    # Keywords
    keywords = data.get("keywords")
    if keywords and isinstance(keywords, list):
        result["keywords"] = [str(k).strip() for k in keywords if str(k).strip()]

    # DOI normalization
    if result["doi"]:
        doi_match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", result["doi"], re.IGNORECASE)
        if doi_match:
            result["doi"] = doi_match.group(1).rstrip(".,;)").lower()

    # Language
    language = data.get("language")
    if language in ("zh", "en"):
        result["language"] = language
    else:
        # Auto-detect
        full_text = " ".join([result["title"] or ""] + result["authors"])
        result["language"] = "zh" if re.search(r"[\u4e00-\u9fff]", full_text) else "en"

    # Confidence
    confidence = data.get("confidence")
    if confidence:
        try:
            conf_float = float(confidence)
            if 0.0 <= conf_float <= 1.0:
                result["confidence"] = conf_float
        except (ValueError, TypeError):
            pass

    return result


def _empty_metadata() -> dict:
    """Return empty metadata dict."""
    return {
        "title": None,
        "authors": [],
        "year": None,
        "journal": None,
        "doi": None,
        "volume": None,
        "issue": None,
        "pages": None,
        "abstract": None,
        "keywords": [],
        "language": "en",
        "confidence": 0.0,
    }
