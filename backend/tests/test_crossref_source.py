"""Tests for Crossref metadata source."""
import pytest
import asyncio


@pytest.mark.asyncio
async def test_crossref_search_by_doi():
    """Should find paper by DOI."""
    from backend.services.crossref_source import CrossrefSource

    source = CrossrefSource()
    # Use a known DOI
    result = await source.search_by_doi("10.1038/s41586-020-2649-2")

    if result is None:
        pytest.skip("Crossref API unavailable")

    assert result.title is not None
    assert len(result.authors) > 0
    assert result.doi == "10.1038/s41586-020-2649-2"
    assert result.source == "crossref"


@pytest.mark.asyncio
async def test_crossref_search_by_title():
    """Should find paper by title."""
    from backend.services.crossref_source import CrossrefSource

    source = CrossrefSource()
    results = await source.search_by_metadata(
        "Deep Learning",
        max_results=3,
    )

    if not results:
        pytest.skip("Crossref API unavailable")

    assert len(results) > 0
    assert results[0].title is not None
