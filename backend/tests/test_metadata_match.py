"""Tests for enhanced metadata matching."""
import pytest


def test_compute_metadata_match_score_doi_exact():
    """DOI exact match should return 1.0."""
    from backend.db.utils import compute_metadata_match_score

    extracted = {"doi": "10.1234/test", "title": "Different Title", "authors": [], "year": None}
    existing = {"doi": "10.1234/test", "title": "Another Title", "authors": [], "year": 2020}

    score = compute_metadata_match_score(extracted, existing)
    assert score == 1.0


def test_compute_metadata_match_score_title_high():
    """Very similar titles should get high score."""
    from backend.db.utils import compute_metadata_match_score

    extracted = {"doi": None, "title": "Digital Financial Inclusion and Economic Growth", "authors": ["Smith"], "year": 2024}
    existing = {"doi": None, "title": "Digital Financial Inclusion and Economic Growth: Evidence from China", "authors": ["Smith"], "year": 2024}

    score = compute_metadata_match_score(extracted, existing)
    assert score >= 0.85


def test_compute_metadata_match_score_no_match():
    """Completely different papers should get low score."""
    from backend.db.utils import compute_metadata_match_score

    extracted = {"doi": None, "title": "Machine Learning in Healthcare", "authors": ["Zhang"], "year": 2023}
    existing = {"doi": None, "title": "Climate Change Impact on Agriculture", "authors": ["Li"], "year": 2020}

    score = compute_metadata_match_score(extracted, existing)
    assert score < 0.5


def test_compute_metadata_match_score_doi_mismatch():
    """Different DOIs should not match."""
    from backend.db.utils import compute_metadata_match_score

    extracted = {"doi": "10.1234/paper1", "title": "Same Title", "authors": [], "year": None}
    existing = {"doi": "10.1234/paper2", "title": "Same Title", "authors": [], "year": None}

    score = compute_metadata_match_score(extracted, existing)
    assert score < 0.92  # Should not be high confidence
