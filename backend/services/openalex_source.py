"""OpenAlex API implementation for metadata lookup."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from backend.services.metadata_sources import CandidateMetadata, MetadataSource

logger = logging.getLogger(__name__)

OPENALEX_API = "https://api.openalex.org"
POLITE_EMAIL = "deep-reading-agent@example.com"


class OpenAlexSource(MetadataSource):
    """OpenAlex API metadata source."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def search_by_doi(self, doi: str) -> Optional[CandidateMetadata]:
        """Search OpenAlex by DOI."""
        url = f"{OPENALEX_API}/works/doi:{doi}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    params={"mailto": POLITE_EMAIL},
                )
                if response.status_code != 200:
                    logger.warning("OpenAlex DOI lookup failed: %d", response.status_code)
                    return None

                data = response.json()
                return self._parse_work(data)
        except Exception as e:
            logger.warning("OpenAlex DOI lookup error: %s", e)
            return None

    async def search_by_metadata(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
        max_results: int = 5,
    ) -> list[CandidateMetadata]:
        """Search OpenAlex by title/authors/year."""
        params = {
            "search": title,
            "per_page": max_results,
            "mailto": POLITE_EMAIL,
        }

        if year:
            params["filter"] = f"publication_year:{year}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{OPENALEX_API}/works",
                    params=params,
                )
                if response.status_code != 200:
                    logger.warning("OpenAlex search failed: %d", response.status_code)
                    return []

                data = response.json()
                results = []
                for work in data.get("results", []):
                    candidate = self._parse_work(work)
                    if candidate:
                        results.append(candidate)

                return results
        except Exception as e:
            logger.warning("OpenAlex search error: %s", e)
            return []

    def _parse_work(self, work: dict) -> Optional[CandidateMetadata]:
        """Parse an OpenAlex work into CandidateMetadata."""
        try:
            title = work.get("title")
            if not title:
                return None

            authors = []
            for authorship in work.get("authorships", []):
                author = authorship.get("author", {})
                name = author.get("display_name")
                if name:
                    authors.append(name)

            year = work.get("publication_year")

            journal = None
            loc = work.get("primary_location", {})
            if loc:
                source = loc.get("source", {})
                if source:
                    journal = source.get("display_name")

            doi = work.get("doi")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi[len("https://doi.org/"):]

            biblio = work.get("biblio", {})
            volume = biblio.get("volume")
            issue = biblio.get("issue")
            first_page = biblio.get("first_page")
            last_page = biblio.get("last_page")
            pages = None
            if first_page and last_page:
                pages = f"{first_page}-{last_page}"
            elif first_page:
                pages = first_page

            return CandidateMetadata(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                doi=doi,
                volume=volume,
                issue=issue,
                pages=pages,
                source="openalex",
                raw_data=work,
            )
        except Exception as e:
            logger.warning("Failed to parse OpenAlex work: %s", e)
            return None
