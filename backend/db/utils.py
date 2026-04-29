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
        return len(shorter) / len(longer)

    return SequenceMatcher(None, left_norm, right_norm).ratio()
