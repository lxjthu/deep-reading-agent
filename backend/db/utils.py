"""Database-related utility helpers."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional, Sequence


def compute_dedup_key(
    doi: Optional[str],
    title: str,
    authors: Optional[Sequence[str]],
    year: Optional[int],
) -> str:
    """Generate a stable signature used to deduplicate bibliography entries.

    Prefers a normalized DOI when available; otherwise falls back to a
    signature derived from first author + year + normalized title.
    """
    if doi:
        clean = doi.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
        clean = clean.strip()
        if clean:
            return f"doi:{clean}"

    first_author = ""
    if authors:
        first_author = (authors[0] or "").strip().lower()
    if not first_author:
        first_author = "unknown"

    title_norm = re.sub(r"[^\w]+", "", (title or "").lower())[:60]
    return f"sig:{first_author}:{year or 0}:{title_norm}"


def normalize_title_for_match(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", (title or "")).strip().lower()
    normalized = re.sub(r"\.[a-z0-9]{1,5}$", "", normalized)
    normalized = re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)
    return normalized


def title_match_score(left: str, right: str) -> float:
    left_norm = normalize_title_for_match(left)
    right_norm = normalize_title_for_match(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    shorter, longer = sorted((left_norm, right_norm), key=len)
    if len(shorter) >= 12 and (shorter in longer or longer.startswith(shorter)):
        return 1.0

    return SequenceMatcher(None, left_norm, right_norm).ratio()


def normalize_doi(value: Optional[str]) -> Optional[str]:
    """Normalize DOI string."""
    if not value:
        return None
    text = value.strip()
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).rstrip(".,;)").lower()


def _extract_surname(author_name: str) -> str:
    """Extract surname from author name string."""
    if not author_name:
        return ""
    name = author_name.strip().strip(".")
    if "," in name:
        return name.split(",")[0].strip().lower()
    parts = name.split()
    if parts:
        return parts[-1].strip().lower()
    return name.lower()


def compute_metadata_match_score(extracted: dict, existing: dict) -> float:
    """Compute match score between extracted metadata and existing bib entry.

    Args:
        extracted: Dict with doi, title, authors, year from PDF extraction
        existing: Dict with doi, title, authors, year from existing bib entry

    Returns:
        Score between 0.0 and 1.0
    """
    doi_ext = normalize_doi(extracted.get("doi"))
    doi_exist = normalize_doi(existing.get("doi"))
    if doi_ext and doi_exist and doi_ext == doi_exist:
        return 1.0

    if doi_ext and doi_exist and doi_ext != doi_exist:
        return 0.1

    title_ext = extracted.get("title") or ""
    title_exist = existing.get("title") or ""
    title_score = title_match_score(title_ext, title_exist) if title_ext and title_exist else 0.0

    authors_ext = extracted.get("authors") or []
    authors_exist = existing.get("authors") or []
    first_author_score = 0.0
    if authors_ext and authors_exist:
        surname_ext = _extract_surname(authors_ext[0])
        surname_exist = _extract_surname(authors_exist[0])
        if surname_ext and surname_exist and surname_ext == surname_exist:
            first_author_score = 1.0

    author_overlap_score = 0.0
    if authors_ext and authors_exist:
        ext_surnames = {_extract_surname(a) for a in authors_ext}
        exist_surnames = {_extract_surname(a) for a in authors_exist}
        ext_surnames.discard("")
        exist_surnames.discard("")
        if ext_surnames and exist_surnames:
            intersection = ext_surnames & exist_surnames
            union = ext_surnames | exist_surnames
            author_overlap_score = len(intersection) / len(union)

    year_score = 0.0
    year_ext = extracted.get("year")
    year_exist = existing.get("year")
    if year_ext and year_exist and year_ext == year_exist:
        year_score = 1.0

    journal_score = 0.0
    journal_ext = extracted.get("journal") or ""
    journal_exist = existing.get("journal") or ""
    if journal_ext and journal_exist:
        j_ext = journal_ext.lower().strip()
        j_exist = journal_exist.lower().strip()
        if j_ext == j_exist:
            journal_score = 1.0
        elif j_ext in j_exist or j_exist in j_ext:
            journal_score = 0.7

    lang_score = 0.0
    lang_ext = extracted.get("language")
    lang_exist = existing.get("language")
    if lang_ext and lang_exist and lang_ext == lang_exist:
        lang_score = 1.0

    total = (
        0.45 * title_score +
        0.20 * first_author_score +
        0.10 * author_overlap_score +
        0.10 * year_score +
        0.10 * journal_score +
        0.05 * lang_score
    )

    return min(total, 0.99)
