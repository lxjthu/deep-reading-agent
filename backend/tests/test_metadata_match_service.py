"""Tests for unified metadata matching service."""
import pytest


def test_score_candidates_returns_sorted():
    """Candidates should be sorted by score descending."""
    from backend.services.metadata_match_service import score_candidates
    from backend.services.metadata_sources import CandidateMetadata

    extracted = {
        "title": "Digital Financial Inclusion",
        "authors": ["Smith"],
        "year": 2024,
        "doi": None,
        "journal": None,
        "language": "en",
    }

    candidates = [
        CandidateMetadata(
            title="Completely Different Paper",
            authors=["Zhang"],
            year=2020,
            journal="Other Journal",
            doi=None,
            volume=None,
            issue=None,
            pages=None,
            source="crossref",
        ),
        CandidateMetadata(
            title="Digital Financial Inclusion and Growth",
            authors=["Smith"],
            year=2024,
            journal="Finance Journal",
            doi="10.1234/test",
            volume=None,
            issue=None,
            pages=None,
            source="openalex",
        ),
    ]

    scored = score_candidates(extracted, candidates)

    assert len(scored) == 2
    assert scored[0].score >= scored[1].score
