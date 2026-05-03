"""Unified metadata matching and scoring service."""
from __future__ import annotations

import logging
from typing import Optional

from backend.db.utils import compute_metadata_match_score
from backend.services.metadata_sources import CandidateMetadata

logger = logging.getLogger(__name__)

# Confidence thresholds
HIGH_CONFIDENCE = 0.92
MEDIUM_CONFIDENCE = 0.78


def score_candidates(
    extracted: dict,
    candidates: list[CandidateMetadata],
) -> list[CandidateMetadata]:
    """
    Score and sort candidates based on extracted metadata.

    Args:
        extracted: Dict with title, authors, year, doi, journal, language
        candidates: List of CandidateMetadata from online sources

    Returns:
        Candidates sorted by score descending, with scores assigned
    """
    for candidate in candidates:
        existing = {
            "title": candidate.title,
            "authors": candidate.authors,
            "year": candidate.year,
            "doi": candidate.doi,
            "journal": candidate.journal,
            "language": None,  # Not always available from online sources
        }
        candidate.score = compute_metadata_match_score(extracted, existing)

    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def classify_confidence(score: float) -> str:
    """
    Classify confidence level based on score.

    Returns:
        "high" if score >= HIGH_CONFIDENCE
        "medium" if score >= MEDIUM_CONFIDENCE
        "low" otherwise
    """
    if score >= HIGH_CONFIDENCE:
        return "high"
    elif score >= MEDIUM_CONFIDENCE:
        return "medium"
    else:
        return "low"


def apply_high_confidence_match(
    bib_entry: dict,
    candidate: CandidateMetadata,
) -> dict:
    """
    Apply high-confidence match to bib entry (only fill empty fields).

    Args:
        bib_entry: Current bib entry dict
        candidate: High-confidence candidate

    Returns:
        Updated bib entry dict
    """
    updates = {}

    # Only fill empty/null fields
    if not bib_entry.get("doi") and candidate.doi:
        updates["doi"] = candidate.doi

    if not bib_entry.get("journal") and candidate.journal:
        updates["journal"] = candidate.journal

    if not bib_entry.get("volume") and candidate.volume:
        updates["volume"] = candidate.volume

    if not bib_entry.get("issue") and candidate.issue:
        updates["issue"] = candidate.issue

    if not bib_entry.get("pages") and candidate.pages:
        updates["pages"] = candidate.pages

    # For authors, only update if current is empty
    current_authors = bib_entry.get("authors") or []
    if not current_authors and candidate.authors:
        updates["authors"] = candidate.authors

    # For year, only update if current is null
    if not bib_entry.get("year") and candidate.year:
        updates["year"] = candidate.year

    # Title: do NOT overwrite existing title (conservative)

    return updates
