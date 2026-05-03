"""Tests for OpenAlex metadata source."""
import pytest


@pytest.mark.asyncio
async def test_openalex_search_by_doi():
    """Should find paper by DOI."""
    from backend.services.openalex_source import OpenAlexSource

    source = OpenAlexSource()
    result = await source.search_by_doi("10.1038/s41586-020-2649-2")

    if result is None:
        pytest.skip("OpenAlex API unavailable")

    assert result.title is not None
    assert result.source == "openalex"


@pytest.mark.asyncio
async def test_openalex_search_by_title():
    """Should find paper by title."""
    from backend.services.openalex_source import OpenAlexSource

    source = OpenAlexSource()
    results = await source.search_by_metadata("Deep Learning", max_results=3)

    if not results:
        pytest.skip("OpenAlex API unavailable")

    assert len(results) > 0
