"""Consent-gated external retrieval helpers for the agent."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BibEntry, User
from services.fulltext_lookup import lookup_fulltext


def build_cnki_title_search_url(title: str) -> str:
    query = title.strip()
    params = urlencode({"kw": query, "korder": "TI"})
    return f"https://kns.cnki.net/kns8s/defaultresult/index?{params}"


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    import json

    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


async def _owned_entries(db: AsyncSession, user: User, entry_ids: list[str]) -> list[BibEntry]:
    if not entry_ids:
        return []
    rows = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == user.id,
                BibEntry.id.in_(entry_ids),
            )
        )
    ).scalars().all()
    by_id = {row.id: row for row in rows}
    return [by_id[entry_id] for entry_id in entry_ids if entry_id in by_id]


async def tool_search_cnki(
    db: AsyncSession,
    user: User,
    *,
    entry_ids: list[str] | None = None,
    titles: list[str] | None = None,
    max_items: int = 20,
) -> dict[str, Any]:
    max_items = max(1, int(max_items or 50))
    entries = await _owned_entries(db, user, [str(item) for item in (entry_ids or []) if item])
    rows: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for entry in entries:
        title = entry.title.strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        rows.append(
            {
                "entry_id": entry.id,
                "title": title,
                "url": build_cnki_title_search_url(title),
                "source_tier": "P3",
                "source": "CNKI",
            }
        )

    for title in titles or []:
        clean_title = str(title).strip()
        if not clean_title or clean_title in seen_titles:
            continue
        seen_titles.add(clean_title)
        rows.append(
            {
                "entry_id": None,
                "title": clean_title,
                "url": build_cnki_title_search_url(clean_title),
                "source_tier": "P3",
                "source": "CNKI",
            }
        )
        if len(rows) >= max_items:
            break

    rows = rows[:max_items]
    return {
        "status": "ready_to_open",
        "tool": "search_cnki",
        "count": len(rows),
        "open_urls": [row["url"] for row in rows],
        "items": rows,
        "note": "这些是 CNKI 题名检索入口，属于临时联网线索，不会自动写入数据库。",
    }


def _candidate_payload(candidate) -> dict[str, Any]:
    return {
        "url": candidate.url,
        "source": candidate.source,
        "version": candidate.version,
        "kind": candidate.kind,
        "label": candidate.label,
        "confidence": candidate.confidence,
    }


async def tool_lookup_english_fulltext(
    db: AsyncSession,
    user: User,
    *,
    entry_ids: list[str],
    max_entries: int = 5,
) -> dict[str, Any]:
    max_entries = max(1, int(max_entries or 10))
    entries = await _owned_entries(db, user, [str(item) for item in (entry_ids or []) if item])
    results: list[dict[str, Any]] = []
    open_urls: list[str] = []
    for entry in entries[:max_entries]:
        lookup = await lookup_fulltext(
            title=entry.title,
            doi=entry.doi,
            authors=_json_list(entry.authors_json),
            year=entry.year,
        )
        pdfs = [_candidate_payload(item) for item in lookup.pdf_candidates]
        pages = [_candidate_payload(item) for item in lookup.landing_pages]
        searches = [_candidate_payload(item) for item in lookup.working_paper_searches]
        for candidate in [*pdfs, *pages, *searches]:
            url = candidate.get("url")
            if url and url not in open_urls:
                open_urls.append(str(url))
        results.append(
            {
                "entry_id": entry.id,
                "title": entry.title,
                "doi": lookup.doi,
                "pdf_candidates": pdfs,
                "landing_pages": pages,
                "working_paper_searches": searches,
            }
        )
    return {
        "status": "ready_to_open",
        "tool": "lookup_english_fulltext",
        "count": len(results),
        "open_urls": open_urls[:50],
        "results": results,
        "note": "这些是英文全文候选和检索入口，Agent 不会自动下载 PDF 或写入数据库。",
    }
