"""Tests for DeepSeek metadata extraction."""
import pytest


def test_extract_metadata_returns_dict():
    """extract_metadata_with_llm should return dict with expected keys."""
    from backend.services.pdf_metadata_llm import extract_metadata_with_llm

    front_matter = {
        "page_1_full": "Test Paper Title\nJohn Smith, Jane Doe\nUniversity of Example\nhttps://doi.org/10.1234/test",
        "page_2_header": "",
        "page_3_header": "",
        "doi_candidates": ["10.1234/test"],
        "isbn_candidates": [],
        "total_pages": 10,
    }

    # This test requires DEEPSEEK_API_KEY, skip if not available
    import os
    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set")

    result = extract_metadata_with_llm(front_matter, "test_paper.pdf")

    assert isinstance(result, dict)
    assert "title" in result
    assert "authors" in result
    assert "year" in result
    assert "doi" in result
    assert "language" in result
