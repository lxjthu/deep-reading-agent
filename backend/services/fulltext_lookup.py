"""Find open full text and working-paper leads for bibliography entries."""
from __future__ import annotations

import logging
import os
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

import httpx

logger = logging.getLogger(__name__)

POLITE_EMAIL = "deep-reading-agent@example.com"
OPENALEX_API = "https://api.openalex.org"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
GOOGLE_SEARCH_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"


def _get_proxy_url() -> str | None:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    if proxy:
        return proxy
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 7890), timeout=0.5):
            return "http://127.0.0.1:7890"
    except OSError:
        return None


def _make_client(**kwargs) -> httpx.AsyncClient:
    proxy = _get_proxy_url()
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.AsyncClient(**kwargs)


@dataclass
class FullTextCandidate:
    url: str
    source: str
    version: str
    kind: str
    label: str
    confidence: float = 0.0


@dataclass
class FullTextLookupResult:
    doi: str | None
    pdf_candidates: list[FullTextCandidate] = field(default_factory=list)
    landing_pages: list[FullTextCandidate] = field(default_factory=list)
    working_paper_searches: list[FullTextCandidate] = field(default_factory=list)


def normalize_doi_for_lookup(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).rstrip(".,;)").lower()


def _add_unique(items: list[FullTextCandidate], candidate: FullTextCandidate) -> None:
    normalized = candidate.url.rstrip("/")
    if normalized and not any(item.url.rstrip("/") == normalized for item in items):
        items.append(candidate)


def _title_query(title: str, authors: list[str] | None = None, year: int | None = None) -> str:
    parts = [title.strip()]
    if authors:
        first_author = authors[0].strip()
        if first_author:
            parts.append(first_author)
    if year:
        parts.append(str(year))
    return " ".join(part for part in parts if part)


def build_working_paper_searches(
    title: str,
    authors: list[str] | None = None,
    year: int | None = None,
) -> list[FullTextCandidate]:
    query = _title_query(title, authors, year)
    quoted = quote_plus(query)
    quoted_wp = quote_plus(f'"{title.strip()}" working paper')
    quoted_pdf = quote_plus(f'"{title.strip()}" filetype:pdf')
    searches = [
        (
            f"https://ideas.repec.org/cgi-bin/htsearch?q={quoted}",
            "RePEc/IDEAS",
            "经济学 working paper 索引",
        ),
        (
            f"https://econpapers.repec.org/scripts/search.pf?ft={quoted}",
            "EconPapers",
            "RePEc 的全文检索入口",
        ),
        (
            f"https://papers.ssrn.com/sol3/results.cfm?RequestTimeout=50000000&txtKey_Words={quoted}",
            "SSRN",
            "社科/经济/金融预印本",
        ),
        (
            f"https://www.nber.org/search?search={quoted}",
            "NBER",
            "经济学 working paper 系列",
        ),
        (
            f"https://www.econstor.eu/simple-search?query={quoted}",
            "EconStor",
            "经济与商业研究开放仓储",
        ),
        (
            f"https://scholar.google.com/scholar?q={quoted_wp}",
            "Google Scholar",
            "working paper 通用检索",
        ),
        (
            f"https://www.google.com/search?q={quoted_pdf}",
            "Google",
            "PDF 通用检索",
        ),
    ]
    return [
        FullTextCandidate(
            url=url,
            source=source,
            version="working_paper_search",
            kind="search",
            label=label,
            confidence=0.45,
        )
        for url, source, label in searches
    ]


def _location_to_candidates(location: dict[str, Any], source_name: str) -> list[FullTextCandidate]:
    candidates: list[FullTextCandidate] = []
    pdf_url = location.get("pdf_url")
    landing_page_url = location.get("landing_page_url")
    version = location.get("version") or "open_access"
    host_source = location.get("source") or {}
    display_name = host_source.get("display_name") or source_name
    if pdf_url:
        candidates.append(
            FullTextCandidate(
                url=pdf_url,
                source=display_name,
                version=version,
                kind="pdf",
                label=f"{display_name} PDF",
                confidence=0.92,
            )
        )
    if landing_page_url:
        candidates.append(
            FullTextCandidate(
                url=landing_page_url,
                source=display_name,
                version=version,
                kind="landing",
                label=f"{display_name} 页面",
                confidence=0.75,
            )
        )
    return candidates


async def _lookup_openalex(doi: str, client: httpx.AsyncClient) -> tuple[list[FullTextCandidate], list[FullTextCandidate]]:
    pdfs: list[FullTextCandidate] = []
    pages: list[FullTextCandidate] = []
    response = await client.get(
        f"{OPENALEX_API}/works/doi:{doi}",
        params={"mailto": POLITE_EMAIL},
    )
    if response.status_code != 200:
        return pdfs, pages

    work = response.json()
    for location_key in ("best_oa_location", "primary_location"):
        location = work.get(location_key)
        if isinstance(location, dict):
            for candidate in _location_to_candidates(location, "OpenAlex"):
                _add_unique(pdfs if candidate.kind == "pdf" else pages, candidate)

    for location in work.get("locations") or []:
        if isinstance(location, dict):
            for candidate in _location_to_candidates(location, "OpenAlex"):
                _add_unique(pdfs if candidate.kind == "pdf" else pages, candidate)

    doi_url = work.get("doi")
    if doi_url:
        _add_unique(
            pages,
            FullTextCandidate(
                url=doi_url,
                source="DOI",
                version="published",
                kind="landing",
                label="DOI 文献主页",
                confidence=0.7,
            ),
        )
    return pdfs, pages


async def _lookup_unpaywall(doi: str, client: httpx.AsyncClient) -> tuple[list[FullTextCandidate], list[FullTextCandidate]]:
    pdfs: list[FullTextCandidate] = []
    pages: list[FullTextCandidate] = []
    response = await client.get(
        f"{UNPAYWALL_API}/{doi}",
        params={"email": POLITE_EMAIL},
    )
    if response.status_code != 200:
        return pdfs, pages

    data = response.json()
    locations = []
    best = data.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)
    locations.extend(loc for loc in data.get("oa_locations") or [] if isinstance(loc, dict))

    for location in locations:
        source = location.get("host_type") or "Unpaywall"
        version = location.get("version") or "open_access"
        pdf_url = location.get("url_for_pdf")
        landing_url = location.get("url")
        if pdf_url:
            _add_unique(
                pdfs,
                FullTextCandidate(
                    url=pdf_url,
                    source=source,
                    version=version,
                    kind="pdf",
                    label=f"Unpaywall {version} PDF",
                    confidence=0.94,
                ),
            )
        if landing_url:
            _add_unique(
                pages,
                FullTextCandidate(
                    url=landing_url,
                    source=source,
                    version=version,
                    kind="landing",
                    label=f"Unpaywall {version} 页面",
                    confidence=0.78,
                ),
            )
    return pdfs, pages


async def _lookup_semantic_scholar(
    title: str,
    doi: str | None,
    client: httpx.AsyncClient,
) -> tuple[list[FullTextCandidate], list[FullTextCandidate]]:
    pdfs: list[FullTextCandidate] = []
    pages: list[FullTextCandidate] = []

    paper_data: dict | None = None
    if doi:
        try:
            resp = await client.get(
                f"{SEMANTIC_SCHOLAR_API}/paper/DOI:{doi}",
                params={"fields": "title,openAccessPdf,externalIds,url"},
            )
            if resp.status_code == 200:
                paper_data = resp.json()
        except Exception:
            pass

    if not paper_data and title.strip():
        try:
            resp = await client.get(
                f"{SEMANTIC_SCHOLAR_API}/paper/search",
                params={
                    "query": title,
                    "limit": 3,
                    "fields": "title,openAccessPdf,externalIds,url",
                },
            )
            if resp.status_code == 200:
                results = resp.json().get("data") or []
                for item in results:
                    score = _title_similarity(title, item.get("title") or "")
                    if score >= 0.80:
                        paper_data = item
                        break
        except Exception:
            pass

    if not paper_data:
        return pdfs, pages

    oa_pdf = paper_data.get("openAccessPdf")
    if isinstance(oa_pdf, dict) and oa_pdf.get("url"):
        _add_unique(
            pdfs,
            FullTextCandidate(
                url=oa_pdf["url"],
                source="Semantic Scholar",
                version="open_access",
                kind="pdf",
                label="Semantic Scholar Open Access PDF",
                confidence=0.90,
            ),
        )

    paper_url = paper_data.get("url")
    if paper_url:
        _add_unique(
            pages,
            FullTextCandidate(
                url=paper_url,
                source="Semantic Scholar",
                version="open_access",
                kind="landing",
                label="Semantic Scholar 页面",
                confidence=0.76,
            ),
        )

    return pdfs, pages


async def _search_google_pdf(
    title: str,
    authors: list[str] | None = None,
    year: int | None = None,
) -> list[FullTextCandidate]:
    pdfs: list[FullTextCandidate] = []
    query_parts = [f'"{title.strip()}"']
    if authors:
        first = authors[0].strip().split(",")[0].strip()
        if first:
            query_parts.append(first)
    query = " ".join(query_parts) + " filetype:pdf"
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=10"

    timeout = httpx.Timeout(connect=15.0, read=20.0, write=10.0, pool=10.0)
    try:
        async with _make_client(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": GOOGLE_SEARCH_UA,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            if resp.status_code != 200:
                return pdfs

            html = resp.text
            href_pattern = re.compile(r'href="(https?://[^"]+\.pdf[^"]*)"', re.IGNORECASE)
            seen: set[str] = set()
            for match in href_pattern.finditer(html):
                link = match.group(1)
                link_clean = link.split("&")[0].rstrip("/")
                if link_clean in seen:
                    continue
                seen.add(link_clean)
                if any(skip in link_clean.lower() for skip in ("google.com", "googleusercontent.com", "schema.org")):
                    continue
                _add_unique(
                    pdfs,
                    FullTextCandidate(
                        url=link_clean,
                        source="Google",
                        version="search_result",
                        kind="pdf",
                        label=f"Google 搜索结果 PDF",
                        confidence=0.65,
                    ),
                )
    except Exception:
        logger.debug("Google PDF search failed", exc_info=True)

    return pdfs


def _title_similarity(left: str, right: str) -> float:
    def normalize(value: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()

    left_norm = normalize(left)
    right_norm = normalize(right)
    if not left_norm or not right_norm:
        return 0.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


async def _find_doi_by_title(
    title: str,
    year: int | None,
    client: httpx.AsyncClient,
) -> str | None:
    params: dict[str, Any] = {
        "search": title,
        "per_page": 3,
        "mailto": POLITE_EMAIL,
    }
    if year:
        params["filter"] = f"publication_year:{year}"

    response = await client.get(f"{OPENALEX_API}/works", params=params)
    if response.status_code != 200:
        return None

    best: tuple[float, str | None] = (0.0, None)
    for work in response.json().get("results", []):
        candidate_title = work.get("title") or ""
        score = _title_similarity(title, candidate_title)
        doi = normalize_doi_for_lookup(work.get("doi"))
        if doi and score > best[0]:
            best = (score, doi)
    return best[1] if best[0] >= 0.82 else None


async def lookup_fulltext(
    *,
    title: str,
    doi: str | None,
    authors: list[str] | None = None,
    year: int | None = None,
) -> FullTextLookupResult:
    clean_doi = normalize_doi_for_lookup(doi)
    result = FullTextLookupResult(doi=clean_doi)

    timeout = httpx.Timeout(connect=15.0, read=25.0, write=15.0, pool=15.0)
    async with _make_client(timeout=timeout, follow_redirects=True) as client:
        if not clean_doi and title.strip():
            try:
                clean_doi = await _find_doi_by_title(title, year, client)
                result.doi = clean_doi
            except Exception:
                clean_doi = None

        if clean_doi:
            for lookup in (_lookup_openalex, _lookup_unpaywall):
                try:
                    pdfs, pages = await lookup(clean_doi, client)
                except Exception:
                    continue
                for candidate in pdfs:
                    _add_unique(result.pdf_candidates, candidate)
                for candidate in pages:
                    _add_unique(result.landing_pages, candidate)

            _add_unique(
                result.landing_pages,
                FullTextCandidate(
                    url=f"https://doi.org/{clean_doi}",
                    source="DOI",
                    version="published",
                    kind="landing",
                    label="DOI 文献主页",
                    confidence=0.7,
                ),
            )

        try:
            s2_pdfs, s2_pages = await _lookup_semantic_scholar(title, clean_doi, client)
            for c in s2_pdfs:
                _add_unique(result.pdf_candidates, c)
            for c in s2_pages:
                _add_unique(result.landing_pages, c)
        except Exception:
            pass

    if title.strip():
        try:
            google_pdfs = await _search_google_pdf(title, authors, year)
            for c in google_pdfs:
                _add_unique(result.pdf_candidates, c)
        except Exception:
            pass

    if not result.pdf_candidates and not result.landing_pages:
        result.working_paper_searches = build_working_paper_searches(title, authors, year)

    result.pdf_candidates.sort(key=lambda item: item.confidence, reverse=True)
    return result


async def download_pdf_candidate(url: str, max_bytes: int = 80 * 1024 * 1024) -> tuple[bytes, str]:
    timeout = httpx.Timeout(connect=20.0, read=60.0, write=20.0, pool=20.0)
    async with _make_client(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/pdf,*/*;q=0.8",
                "User-Agent": "DeepReadingAgent/1.0 (+https://example.com)",
            },
        )
        response.raise_for_status()
        content = response.content
        if len(content) > max_bytes:
            raise ValueError("PDF 文件过大，已跳过自动挂载。")
        content_type = response.headers.get("content-type", "")
        if not content.lstrip().startswith(b"%PDF") and "pdf" not in content_type.lower():
            raise ValueError("候选链接未返回 PDF 文件。")
        return content, str(response.url)
