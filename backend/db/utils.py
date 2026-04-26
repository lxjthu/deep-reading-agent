"""Database-related utility helpers."""
from __future__ import annotations

import re
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
