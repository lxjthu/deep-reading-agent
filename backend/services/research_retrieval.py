"""Tiered lexical retrieval for the research agent."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Annotation,
    BibEntry,
    BibReference,
    BibReferenceCitation,
    CardNote,
    File,
    ReadingItem,
    ReadingItemEdit,
    ReadingSourceEvidence,
)
from upload_storage import resolve_storage_path


TIER_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
TIER_BASE_SCORE = {"P0": 100.0, "P1": 70.0, "P2": 45.0, "P3": 25.0}
FIELD_WEIGHTS = {
    "doi": 30.0,
    "title": 22.0,
    "abstract": 15.0,
    "source_window": 18.0,
    "reference": 14.0,
    "citation": 18.0,
    "user_note": 15.0,
    "edited_reading_item": 13.0,
    "annotation": 11.0,
    "card_note": 10.0,
    "source_evidence": 24.0,
    "reading_item": 7.0,
}


@dataclass(slots=True)
class ResearchQuery:
    question: str
    entry_ids: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    include_source_text: bool = True
    include_user_notes: bool = True
    include_ai_notes: bool = True
    limit_entries: int = 0
    limit_evidence_per_entry: int = 8


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _terms(query: ResearchQuery) -> list[str]:
    values = [query.question, *query.keywords]
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        for term in re.findall(r"[\w\u4e00-\u9fff.-]+", value.lower()):
            if len(term) < 2 or term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def _contains_any(text: str | None, terms: list[str]) -> bool:
    if not terms:
        return True
    lowered = (text or "").lower()
    return any(term in lowered for term in terms)


def _dialect_name(db: AsyncSession) -> str:
    try:
        return db.get_bind().dialect.name
    except Exception:
        return ""


def _source_evidence_match_filter(db: AsyncSession, terms: list[str], likes: list[str]):
    predicates = [
        *[ReadingSourceEvidence.quote_text.ilike(like) for like in likes],
        *[ReadingSourceEvidence.claim_text.ilike(like) for like in likes],
        *[ReadingSourceEvidence.section_hint.ilike(like) for like in likes],
    ]
    if _dialect_name(db) == "postgresql" and terms:
        text_expr = (
            func.coalesce(ReadingSourceEvidence.quote_text, "")
            + literal(" ")
            + func.coalesce(ReadingSourceEvidence.claim_text, "")
            + literal(" ")
            + func.coalesce(ReadingSourceEvidence.section_hint, "")
        )
        predicates.append(
            func.to_tsvector("simple", text_expr).op("@@")(
                func.plainto_tsquery("simple", " ".join(terms))
            )
        )
    return or_(*predicates)


def _coverage(text: str | None, terms: list[str]) -> float:
    if not terms:
        return 0.0
    lowered = (text or "").lower()
    return sum(1 for term in terms if term in lowered) / max(len(terms), 1)


def _snippet(text: str | None, terms: list[str], limit: int = 520) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    lowered = clean.lower()
    hit_positions = [lowered.find(term) for term in terms if term and lowered.find(term) >= 0]
    center = min(hit_positions) if hit_positions else 0
    start = max(0, center - limit // 3)
    end = min(len(clean), start + limit)
    if end - start < limit:
        start = max(0, end - limit)
    prefix = "..." if start else ""
    suffix = "..." if end < len(clean) else ""
    return f"{prefix}{clean[start:end]}{suffix}"


def _entry_summary(entry: BibEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "title": entry.title,
        "authors": _json_list(entry.authors_json),
        "year": entry.year,
        "journal": entry.journal,
        "doi": entry.doi,
        "reading_status": entry.reading_status,
    }


def _score(source_tier: str, source_kind: str, text: str | None, terms: list[str]) -> float:
    return round(
        TIER_BASE_SCORE[source_tier]
        + FIELD_WEIGHTS.get(source_kind, 0.0)
        + (_coverage(text, terms) * 10.0),
        3,
    )


def _evidence(
    *,
    entry_id: str,
    source_tier: str,
    source_kind: str,
    table: str,
    text: str | None,
    terms: list[str],
    row_id: str | int | None = None,
    field_name: str | None = None,
    item_label: str | None = None,
    page_label: str | None = None,
    heading_path: str | None = None,
) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "source_tier": source_tier,
        "source_kind": source_kind,
        "table": table,
        "row_id": str(row_id) if row_id is not None else None,
        "field": field_name,
        "item_label": item_label,
        "page_label": page_label,
        "heading_path": heading_path,
        "quote": _snippet(text, terms),
        "score": _score(source_tier, source_kind, text, terms),
    }


def _sort_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            TIER_ORDER.get(str(item.get("source_tier")), 99),
            -float(item.get("score") or 0),
            str(item.get("source_kind") or ""),
        ),
    )


async def _load_entries(db: AsyncSession, owner_user_id: int, query: ResearchQuery, terms: list[str]) -> list[BibEntry]:
    limit = max(1, int(query.limit_entries or 100))
    stmt = _base_entry_stmt(owner_user_id, query, terms)
    rows = (await db.execute(stmt.order_by(BibEntry.updated_at.desc()).limit(limit))).scalars().all()
    entries_by_id = {entry.id: entry for entry in rows}

    if terms and not query.entry_ids:
        likes = [f"%{term}%" for term in terms]
        related_ids: set[str] = set()

        reading_ids = (
            await db.execute(
                select(ReadingItem.bib_entry_id)
                .where(
                    ReadingItem.owner_user_id == owner_user_id,
                    or_(
                        *[ReadingItem.content.ilike(like) for like in likes],
                        *[ReadingItem.item_label.ilike(like) for like in likes],
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        related_ids.update(str(item) for item in reading_ids)

        edited_ids = (
            await db.execute(
                select(ReadingItem.bib_entry_id)
                .join(ReadingItemEdit, ReadingItemEdit.reading_item_id == ReadingItem.id)
                .where(
                    ReadingItem.owner_user_id == owner_user_id,
                    ReadingItemEdit.owner_user_id == owner_user_id,
                    or_(*[ReadingItemEdit.edited_content.ilike(like) for like in likes]),
                )
                .limit(limit)
            )
        ).scalars().all()
        related_ids.update(str(item) for item in edited_ids)

        if query.include_source_text:
            source_evidence_ids = (
                await db.execute(
                    select(ReadingSourceEvidence.bib_entry_id)
                    .where(
                        ReadingSourceEvidence.owner_user_id == owner_user_id,
                        ReadingSourceEvidence.source_tier == "P0",
                        ReadingSourceEvidence.validation_status.in_(["exact", "fuzzy"]),
                        _source_evidence_match_filter(db, terms, likes),
                    )
                    .limit(limit)
                )
            ).scalars().all()
            related_ids.update(str(item) for item in source_evidence_ids)

        annotation_ids = (
            await db.execute(
                select(Annotation.bib_entry_id)
                .where(
                    Annotation.owner_user_id == owner_user_id,
                    Annotation.bib_entry_id.is_not(None),
                    or_(
                        *[Annotation.note.ilike(like) for like in likes],
                        *[Annotation.selected_text.ilike(like) for like in likes],
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        related_ids.update(str(item) for item in annotation_ids if item)

        card_ids = (
            await db.execute(
                select(CardNote.source_bib_entry_id)
                .where(
                    CardNote.owner_user_id == owner_user_id,
                    or_(
                        *[CardNote.title.ilike(like) for like in likes],
                        *[CardNote.summary.ilike(like) for like in likes],
                        *[CardNote.selected_text.ilike(like) for like in likes],
                        *[CardNote.body_markdown.ilike(like) for like in likes],
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        related_ids.update(str(item) for item in card_ids)

        reference_ids = (
            await db.execute(
                select(BibReference.source_bib_entry_id)
                .where(
                    BibReference.owner_user_id == owner_user_id,
                    or_(
                        *[BibReference.raw_text.ilike(like) for like in likes],
                        *[BibReference.title.ilike(like) for like in likes],
                        *[BibReference.doi.ilike(like) for like in likes],
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        related_ids.update(str(item) for item in reference_ids)

        citation_ids = (
            await db.execute(
                select(BibReferenceCitation.source_bib_entry_id)
                .where(
                    BibReferenceCitation.owner_user_id == owner_user_id,
                    or_(
                        *[BibReferenceCitation.quote_text.ilike(like) for like in likes],
                        *[BibReferenceCitation.quote_text_zh.ilike(like) for like in likes],
                        *[BibReferenceCitation.excerpt.ilike(like) for like in likes],
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        related_ids.update(str(item) for item in citation_ids)

        missing_ids = [entry_id for entry_id in related_ids if entry_id not in entries_by_id]
        if missing_ids:
            related_entries = (
                await db.execute(
                    select(BibEntry).where(
                        BibEntry.owner_user_id == owner_user_id,
                        BibEntry.id.in_(missing_ids),
                    )
                )
            ).scalars().all()
            for entry in related_entries:
                entries_by_id[entry.id] = entry

    entries = list(entries_by_id.values())
    entries.sort(key=lambda entry: _coverage(" ".join([entry.title, entry.abstract or "", entry.user_note or ""]), terms), reverse=True)
    return entries[:limit]


BATCH_SIZE = 100


def _base_entry_stmt(owner_user_id: int, query: ResearchQuery, terms: list[str]):
    """Build the base SELECT for bib_entries matching query terms."""
    stmt = select(BibEntry).where(BibEntry.owner_user_id == owner_user_id)
    if query.entry_ids:
        stmt = stmt.where(BibEntry.id.in_(query.entry_ids))
    elif terms:
        likes = [f"%{term}%" for term in terms]
        stmt = stmt.where(
            or_(
                *[BibEntry.title.ilike(like) for like in likes],
                *[BibEntry.abstract.ilike(like) for like in likes],
                *[BibEntry.abstract_cn.ilike(like) for like in likes],
                *[BibEntry.journal.ilike(like) for like in likes],
                *[BibEntry.doi.ilike(like) for like in likes],
                *[BibEntry.keywords_json.ilike(like) for like in likes],
                *[BibEntry.user_tags_json.ilike(like) for like in likes],
                *[BibEntry.user_note.ilike(like) for like in likes],
            )
        )
    return stmt


async def _load_all_entries(
    db: AsyncSession,
    owner_user_id: int,
    query: ResearchQuery,
    terms: list[str],
) -> list[BibEntry]:
    """Load all matching entries, paginating in batches of BATCH_SIZE."""
    stmt = _base_entry_stmt(owner_user_id, query, terms)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    if total <= BATCH_SIZE:
        rows = (await db.execute(stmt.order_by(BibEntry.updated_at.desc()))).scalars().all()
        return _rank_entries(list(rows), terms)

    all_entries: list[BibEntry] = []
    for offset in range(0, total, BATCH_SIZE):
        batch = (
            await db.execute(stmt.order_by(BibEntry.updated_at.desc()).offset(offset).limit(BATCH_SIZE))
        ).scalars().all()
        all_entries.extend(batch)
    return _rank_entries(all_entries, terms)


def _rank_entries(entries: list[BibEntry], terms: list[str]) -> list[BibEntry]:
    """Sort entries by keyword coverage (best match first)."""
    entries.sort(
        key=lambda entry: _coverage(
            " ".join([entry.title, entry.abstract or "", entry.user_note or ""]),
            terms,
        ),
        reverse=True,
    )
    return entries


async def get_source_windows(
    db: AsyncSession,
    *,
    owner_user_id: int,
    entry_ids: list[str],
    question: str = "",
    max_windows_per_entry: int = 3,
) -> dict[str, Any]:
    terms = _terms(ResearchQuery(question=question))
    entries = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == owner_user_id,
                BibEntry.id.in_(entry_ids),
            )
        )
    ).scalars().all()
    windows: list[dict[str, Any]] = []
    limitations: list[str] = []
    for entry in entries:
        file_id = entry.markdown_source_file_id or entry.source_file_id
        file_record = await db.get(File, file_id) if file_id else None
        if not file_record or file_record.owner_user_id != owner_user_id:
            limitations.append(f"{entry.title}: 未绑定可检索原文文件")
            continue
        if file_record.file_type != "markdown":
            limitations.append(f"{entry.title}: PDF 原文检索一期暂不做即时抽取，请先绑定 Markdown 原文或运行精读/翻译")
            continue
        path = resolve_storage_path(file_record.storage_path)
        if not path.exists() or not path.is_file():
            limitations.append(f"{entry.title}: Markdown 原文文件不存在")
            continue
        text = _strip_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
        hits = _source_hits(text, terms, max_windows_per_entry)
        for hit in hits:
            windows.append(
                {
                    "entry_id": entry.id,
                    "title": entry.title,
                    "source_tier": "P0",
                    "source_kind": "source_window",
                    "file_id": file_record.id,
                    "file_name": file_record.original_name,
                    **hit,
                }
            )
    return {"windows": windows, "limitations": limitations}


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :]
    return text


def _heading_path(text: str, offset: int) -> str | None:
    headings: list[str] = []
    consumed = 0
    for line in text.splitlines(True):
        if consumed > offset:
            break
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            level = len(match.group(1))
            headings = headings[: level - 1] + [match.group(2)]
        consumed += len(line)
    return " / ".join(headings) if headings else None


def _source_hits(text: str, terms: list[str], limit: int) -> list[dict[str, Any]]:
    if not text:
        return []
    lowered = text.lower()
    positions = sorted({lowered.find(term) for term in terms if lowered.find(term) >= 0})
    if not positions and not terms:
        positions = [0]
    hits = []
    for pos in positions[: max(1, limit)]:
        start = max(0, pos - 260)
        end = min(len(text), pos + 520)
        hits.append(
            {
                "heading_path": _heading_path(text, pos),
                "char_start": start,
                "char_end": end,
                "quote": _snippet(text[start:end], terms),
                "score": _score("P0", "source_window", text[start:end], terms),
            }
        )
    return hits


async def _collect_entry_evidence(
    db: AsyncSession,
    *,
    owner_user_id: int,
    entry: BibEntry,
    query: ResearchQuery,
    terms: list[str],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    fields = [
        ("title", entry.title, "title"),
        ("abstract", entry.abstract, "abstract"),
        ("abstract", entry.abstract_cn, "abstract_cn"),
        ("doi", entry.doi, "doi"),
        ("abstract", entry.journal, "journal"),
        ("abstract", " ".join(_json_list(entry.keywords_json)), "keywords_json"),
    ]
    for source_kind, text, field_name in fields:
        if _contains_any(text, terms):
            evidence.append(
                _evidence(
                    entry_id=entry.id,
                    source_tier="P0",
                    source_kind=source_kind,
                    table="bib_entries",
                    row_id=entry.id,
                    field_name=field_name,
                    text=text,
                    terms=terms,
                )
            )

    if query.include_source_text:
        source_rows = (
            await db.execute(
                select(ReadingSourceEvidence)
                .where(
                    ReadingSourceEvidence.owner_user_id == owner_user_id,
                    ReadingSourceEvidence.bib_entry_id == entry.id,
                    ReadingSourceEvidence.source_tier == "P0",
                    ReadingSourceEvidence.validation_status.in_(["exact", "fuzzy"]),
                )
                .order_by(ReadingSourceEvidence.id)
            )
        ).scalars().all()
        for row in source_rows:
            match_text = "\n".join(
                part for part in [row.claim_text, row.quote_text, row.section_hint] if part
            )
            if _contains_any(match_text, terms):
                evidence.append(
                    _evidence(
                        entry_id=entry.id,
                        source_tier="P0",
                        source_kind="source_evidence",
                        table="reading_source_evidence",
                        row_id=row.id,
                        field_name="quote_text",
                        item_label=row.item_label,
                        page_label=row.page_label,
                        heading_path=row.heading_path or row.section_hint,
                        text=row.quote_text,
                        terms=terms,
                    )
                )

    if query.include_user_notes and _contains_any(entry.user_note, terms):
        evidence.append(
            _evidence(
                entry_id=entry.id,
                source_tier="P1",
                source_kind="user_note",
                table="bib_entries",
                row_id=entry.id,
                field_name="user_note",
                text=entry.user_note,
                terms=terms,
            )
        )

    edit_rows = (
        await db.execute(
            select(ReadingItem, ReadingItemEdit)
            .join(ReadingItemEdit, ReadingItemEdit.reading_item_id == ReadingItem.id)
            .where(
                ReadingItem.owner_user_id == owner_user_id,
                ReadingItemEdit.owner_user_id == owner_user_id,
                ReadingItem.bib_entry_id == entry.id,
            )
            .order_by(ReadingItem.sort_order)
        )
    ).all()
    for item, edit in edit_rows:
        if query.include_user_notes and _contains_any(edit.edited_content, terms):
            evidence.append(
                _evidence(
                    entry_id=entry.id,
                    source_tier="P1",
                    source_kind="edited_reading_item",
                    table="reading_item_edits",
                    row_id=edit.id,
                    item_label=item.item_label,
                    text=edit.edited_content,
                    terms=terms,
                )
            )

    annotations = (
        await db.execute(
            select(Annotation)
            .where(
                Annotation.owner_user_id == owner_user_id,
                Annotation.bib_entry_id == entry.id,
            )
            .order_by(Annotation.updated_at.desc())
        )
    ).scalars().all()
    for annotation in annotations:
        tier = "P2" if annotation.is_ai_generated else "P1"
        if tier == "P2" and not query.include_ai_notes:
            continue
        if tier == "P1" and not query.include_user_notes:
            continue
        text = "\n".join(part for part in [annotation.selected_text, annotation.note] if part)
        if _contains_any(text, terms):
            evidence.append(
                _evidence(
                    entry_id=entry.id,
                    source_tier=tier,
                    source_kind="annotation",
                    table="annotations",
                    row_id=annotation.id,
                    text=text,
                    terms=terms,
                )
            )

    cards = (
        await db.execute(
            select(CardNote)
            .where(CardNote.owner_user_id == owner_user_id, CardNote.source_bib_entry_id == entry.id)
            .order_by(CardNote.updated_at.desc())
        )
    ).scalars().all()
    for card in cards:
        if not query.include_user_notes:
            continue
        text = "\n".join(part for part in [card.title, card.summary, card.selected_text, card.body_markdown] if part)
        if _contains_any(text, terms):
            evidence.append(
                _evidence(
                    entry_id=entry.id,
                    source_tier="P1",
                    source_kind="card_note",
                    table="card_notes",
                    row_id=card.id,
                    text=text,
                    terms=terms,
                )
            )

    if query.include_ai_notes:
        items = (
            await db.execute(
                select(ReadingItem)
                .where(ReadingItem.owner_user_id == owner_user_id, ReadingItem.bib_entry_id == entry.id)
                .order_by(ReadingItem.sort_order)
            )
        ).scalars().all()
        for item in items:
            text = "\n".join([item.item_label, item.content])
            if _contains_any(text, terms):
                evidence.append(
                    _evidence(
                        entry_id=entry.id,
                        source_tier="P2",
                        source_kind="reading_item",
                        table="reading_items",
                        row_id=item.id,
                        item_label=item.item_label,
                        text=text,
                        terms=terms,
                    )
                )

    references = (
        await db.execute(
            select(BibReference)
            .where(BibReference.owner_user_id == owner_user_id, BibReference.source_bib_entry_id == entry.id)
            .order_by(BibReference.reference_order)
        )
    ).scalars().all()
    for reference in references:
        text = "\n".join(part for part in [reference.raw_text, reference.title, reference.doi] if part)
        if _contains_any(text, terms):
            evidence.append(
                _evidence(
                    entry_id=entry.id,
                    source_tier="P0",
                    source_kind="reference",
                    table="bib_references",
                    row_id=reference.id,
                    text=text,
                    terms=terms,
                )
            )

    citations = (
        await db.execute(
            select(BibReferenceCitation)
            .where(BibReferenceCitation.owner_user_id == owner_user_id, BibReferenceCitation.source_bib_entry_id == entry.id)
            .order_by(BibReferenceCitation.citation_index)
        )
    ).scalars().all()
    for citation in citations:
        text = "\n".join(part for part in [citation.quote_text, citation.excerpt] if part)
        if _contains_any(text, terms):
            evidence.append(
                _evidence(
                    entry_id=entry.id,
                    source_tier="P0",
                    source_kind="citation",
                    table="bib_reference_citations",
                    row_id=citation.id,
                    page_label=citation.page_label,
                    text=text,
                    terms=terms,
                )
            )

    if query.include_source_text:
        windows = await get_source_windows(
            db,
            owner_user_id=owner_user_id,
            entry_ids=[entry.id],
            question=query.question,
            max_windows_per_entry=2,
        )
        for window in windows["windows"]:
            evidence.append(
                _evidence(
                    entry_id=entry.id,
                    source_tier="P0",
                    source_kind="source_window",
                    table="files",
                    row_id=window.get("file_id"),
                    text=window.get("quote"),
                    terms=terms,
                    heading_path=window.get("heading_path"),
                )
            )

    return _sort_evidence(evidence)


async def get_evidence_pack(
    db: AsyncSession,
    *,
    owner_user_id: int,
    query: ResearchQuery,
) -> dict[str, Any]:
    terms = _terms(query)
    if query.limit_entries == 0:
        entries = await _load_all_entries(db, owner_user_id, query, terms)
    else:
        entries = await _load_entries(db, owner_user_id, query, terms)
    limit_evidence = max(1, min(int(query.limit_evidence_per_entry or 8), 200))
    result_entries: list[dict[str, Any]] = []
    for entry in entries:
        evidence = await _collect_entry_evidence(
            db,
            owner_user_id=owner_user_id,
            entry=entry,
            query=query,
            terms=terms,
        )
        if evidence or query.entry_ids:
            result_entries.append(
                {
                    **_entry_summary(entry),
                    "evidence": evidence[:limit_evidence],
                    "conflicts": [],
                }
            )
    result_entries.sort(
        key=lambda item: (
            -max([float(evidence.get("score") or 0) for evidence in item["evidence"]] or [0]),
            item["title"],
        )
    )
    if query.limit_entries == 0:
        entries_limit = len(result_entries)
    else:
        entries_limit = max(1, min(int(query.limit_entries or 100), len(result_entries)))
    return {
        "question": query.question,
        "entries": result_entries[:entries_limit],
        "external_evidence": [],
        "limitations": ["未联网检索；如需最新外部证据，需要先获得用户明确授权。"],
    }


async def research_search(
    db: AsyncSession,
    *,
    owner_user_id: int,
    query: ResearchQuery,
) -> dict[str, Any]:
    pack = await get_evidence_pack(db, owner_user_id=owner_user_id, query=query)
    return {
        "question": pack["question"],
        "count": len(pack["entries"]),
        "entries": pack["entries"],
        "limitations": pack["limitations"],
    }
