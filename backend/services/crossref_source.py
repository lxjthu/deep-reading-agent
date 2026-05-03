"""Crossref API implementation for metadata lookup."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import httpx

from backend.services.metadata_sources import CandidateMetadata, MetadataSource

logger = logging.getLogger(__name__)

CROSSREF_API = "https://api.crossref.org"
# Use mailto for polite pool (higher rate limits)
POLITE_EMAIL = "deep-reading-agent@example.com"


class CrossrefSource(MetadataSource):
    """Crossref API metadata source."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search_by_doi(self, doi: str) -> Optional[CandidateMetadata]:
        """Search Crossref by DOI."""
        url = f"{CROSSREF_API}/works/{doi}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params={"mailto": POLITE_EMAIL},
                )
                if response.status_code != 200:
                    logger.warning("Crossref DOI lookup failed: %d", response.status_code)
                    return None

                data = response.json()
                item = data.get("message", {})
                return self._parse_item(item)
        except Exception as e:
            logger.warning("Crossref DOI lookup error: %s", e)
            return None

    async def search_by_metadata(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
        max_results: int = 5,
    ) -> list[CandidateMetadata]:
        """Search Crossref by title/authors/year."""
        params = {
            "query": title,
            "rows": max_results,
            "mailto": POLITE_EMAIL,
        }

        # Add author filter if available
        if authors:
            params["query.author"] = authors[0]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{CROSSREF_API}/works",
                    params=params,
                )
                if response.status_code != 200:
                    logger.warning("Crossref search failed: %d", response.status_code)
                    return []

                data = response.json()
                items = data.get("message", {}).get("items", [])

                results = []
                for item in items:
                    candidate = self._parse_item(item)
                    if candidate:
                        results.append(candidate)

                return results
        except Exception as e:
            logger.warning("Crossref search error: %s", e)
            return []

    def _parse_item(self, item: dict) -> Optional[CandidateMetadata]:
        """Parse a Crossref work item into CandidateMetadata."""
        try:
            # Title
            title_list = item.get("title", [])
            title = title_list[0] if title_list else None
            if not title:
                return None

            # Authors
            authors = []
            for author in item.get("author", []):
                given = author.get("given", "")
                family = author.get("family", "")
                if family:
                    authors.append(f"{given} {family}".strip())

            # Year
            year = None
            published = item.get("published-print") or item.get("published-online")
            if published:
                date_parts = published.get("date-parts", [[]])
                if date_parts and date_parts[0]:
                    year = date_parts[0][0]

            # Journal
            container = item.get("container-title", [])
            journal = container[0] if container else None

            # DOI
            doi = item.get("DOI")

            # Volume, Issue, Pages
            volume = item.get("volume")
            issue = item.get("issue")
            pages = item.get("page")

            return CandidateMetadata(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                doi=doi,
                volume=volume,
                issue=issue,
                pages=pages,
                source="crossref",
                raw_data=item,
            )
        except Exception as e:
            logger.warning("Failed to parse Crossref item: %s", e)
            return None
