"""Tests for PDF front matter extraction."""
import pytest
from pathlib import Path


def test_extract_front_matter_returns_dict():
    """extract_front_matter should return a dict with expected keys."""
    from backend.services.pdf_metadata_extract import extract_front_matter

    pdf_path = Path(__file__).parent.parent.parent / "_uploads" / "1"
    pdf_files = list(pdf_path.glob("*.pdf")) if pdf_path.exists() else []

    if not pdf_files:
        pytest.skip("No test PDF available")

    result = extract_front_matter(str(pdf_files[0]))

    assert isinstance(result, dict)
    assert "page_1_full" in result
    assert "page_2_header" in result
    assert "page_3_header" in result
    assert "doi_candidates" in result
    assert "isbn_candidates" in result


def test_extract_front_matter_finds_doi():
    """Should extract DOI from PDF text."""
    from backend.services.pdf_metadata_extract import extract_dois

    text = "This paper is published at https://doi.org/10.1234/example.2024.001"
    dois = extract_dois(text)

    assert len(dois) == 1
    assert dois[0] == "10.1234/example.2024.001"


def test_extract_dois_empty():
    """Should return empty list when no DOI found."""
    from backend.services.pdf_metadata_extract import extract_dois

    text = "This is a paper without any DOI information."
    dois = extract_dois(text)

    assert dois == []
