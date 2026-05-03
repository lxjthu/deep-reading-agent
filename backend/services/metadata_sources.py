"""Abstract base class and data structures for metadata sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CandidateMetadata:
    """Candidate metadata from an online source."""
    title: str
    authors: list[str]
    year: Optional[int]
    journal: Optional[str]
    doi: Optional[str]
    volume: Optional[str]
    issue: Optional[str]
    pages: Optional[str]
    source: str  # crossref/openalex/local
    score: float = 0.0  # Match score assigned by scoring service
    raw_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "journal": self.journal,
            "doi": self.doi,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "source": self.source,
            "score": self.score,
        }


class MetadataSource(ABC):
    """Abstract base class for metadata online sources."""

    @abstractmethod
    async def search_by_doi(self, doi: str) -> Optional[CandidateMetadata]:
        """
        Search by DOI and return a single candidate.

        Args:
            doi: Normalized DOI string

        Returns:
            CandidateMetadata if found, None otherwise
        """

    @abstractmethod
    async def search_by_metadata(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
        max_results: int = 5,
    ) -> list[CandidateMetadata]:
        """
        Search by title/authors/year and return candidates.

        Args:
            title: Paper title
            authors: Optional list of author names
            year: Optional publication year
            max_results: Maximum number of results to return

        Returns:
            List of CandidateMetadata, sorted by relevance
        """
