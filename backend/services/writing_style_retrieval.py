"""Read-only original-source retrieval for writing-style analysis."""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BibEntry, File
from upload_storage import resolve_storage_path


STYLE_FOCUS_ALIASES = {
    "introduction": ("引言", "导论", "绪论", "introduction", "intro"),
    "theory": ("理论", "文献综述", "假设", "机制", "theory", "hypothesis", "mechanism"),
    "method": ("方法", "数据", "模型", "识别", "实证", "method", "methods", "data", "empirical", "identification"),
}


def _compact_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def detect_style_focus(question: str | None) -> str:
    lowered = _compact_text(question).lower()
    for focus, aliases in STYLE_FOCUS_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            return focus
    return "general"


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end >= 0:
            return text[end + 4 :]
    return text


def _matches_section(heading: str, section_type: str) -> bool:
    if section_type == "general":
        return True
    aliases = STYLE_FOCUS_ALIASES.get(section_type, ())
    lowered = heading.lower()
    return any(alias.lower() in lowered for alias in aliases)


def _section_quote(text: str, limit: int = 2400) -> str:
    clean = _compact_text(text)
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "..."


GENERAL_STYLE_BUCKETS = (
    ("front", ("摘要", "abstract", "引言", "导论", "绪论", "introduction", "intro")),
    ("theory", ("理论", "文献综述", "假设", "机制", "theory", "literature", "hypothesis", "mechanism")),
    ("method", ("方法", "数据", "模型", "识别", "实证", "method", "methods", "data", "model", "empirical", "identification")),
    ("result", ("结果", "发现", "分析", "稳健", "异质", "result", "results", "finding", "analysis", "robust", "heterogeneity")),
    ("discussion", ("讨论", "结论", "启示", "局限", "conclusion", "discussion", "implication", "limitation")),
)


def _general_bucket(heading_path: str | None) -> str:
    lowered = (heading_path or "").lower()
    for bucket, aliases in GENERAL_STYLE_BUCKETS:
        if any(alias.lower() in lowered for alias in aliases):
            return bucket
    return "other"


def _select_diverse_sections(sections: list[dict[str, Any]], max_sections: int) -> list[dict[str, Any]]:
    limit = max(1, int(max_sections or 1))
    if len(sections) <= limit:
        return sections

    selected: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    for bucket, _aliases in GENERAL_STYLE_BUCKETS:
        for section in sections:
            if id(section) in used_ids:
                continue
            if _general_bucket(section.get("heading_path")) == bucket:
                selected.append(section)
                used_ids.add(id(section))
                break
            if len(selected) >= limit:
                return selected

    for section in sections:
        if id(section) in used_ids:
            continue
        selected.append(section)
        used_ids.add(id(section))
        if len(selected) >= limit:
            break
    return selected


def extract_style_sections(text: str, section_type: str = "general", max_sections: int = 3) -> list[dict[str, Any]]:
    clean = _strip_frontmatter(text or "")
    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    matches = list(heading_re.finditer(clean))
    if not matches:
        quote = _section_quote(clean)
        return [
            {
                "section_type": section_type,
                "heading_path": None,
                "char_start": 0,
                "char_end": min(len(clean), len(quote)),
                "quote": quote,
            }
        ] if quote else []

    sections: list[dict[str, Any]] = []
    path: list[str] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        path = path[: level - 1] + [heading]
        heading_path = " / ".join(path)
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(clean)
        if not _matches_section(heading_path, section_type):
            continue
        body = clean[body_start:body_end].strip()
        quote = _section_quote(body)
        if not quote:
            continue
        sections.append(
            {
                "section_type": section_type,
                "heading_path": heading_path,
                "char_start": body_start,
                "char_end": body_end,
                "quote": quote,
            }
        )

    if section_type == "general":
        return _select_diverse_sections(sections, max_sections)
    return sections[: max(1, int(max_sections or 1))]

def _entry_summary(entry: BibEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "title": entry.title,
        "authors": _json_list(entry.authors_json),
        "year": entry.year,
        "journal": entry.journal,
        "reading_status": entry.reading_status,
    }


async def select_style_entries(
    db: AsyncSession,
    *,
    owner_user_id: int,
    question: str,
    author_or_journal: str | None = None,
    entry_ids: list[str] | None = None,
    limit_entries: int = 5,
) -> list[BibEntry]:
    limit = max(1, min(int(limit_entries or 5), 20))
    stmt = select(BibEntry).where(BibEntry.owner_user_id == owner_user_id)
    explicit_ids = [str(item) for item in (entry_ids or []) if str(item).strip()]
    if explicit_ids:
        stmt = stmt.where(BibEntry.id.in_(explicit_ids))
        rows = (await db.execute(stmt.order_by(BibEntry.updated_at.desc()).limit(limit))).scalars().all()
        return list(rows)

    probe = _compact_text(author_or_journal)
    if probe:
        rows = (await db.execute(stmt.order_by(BibEntry.updated_at.desc()).limit(max(limit, 100)))).scalars().all()
        matched = []
        probe_lower = probe.lower()
        for entry in rows:
            haystack = " ".join([entry.title or "", entry.journal or "", * _json_list(entry.authors_json)]).lower()
            if probe_lower in haystack:
                matched.append(entry)
            if len(matched) >= limit:
                break
        return matched

    value = _compact_text(question)
    if value:
        like = f"%{value}%"
        stmt = stmt.where(
            or_(
                BibEntry.title.ilike(like),
                BibEntry.journal.ilike(like),
                BibEntry.authors_json.ilike(like),
            )
        )
    rows = (await db.execute(stmt.order_by(BibEntry.updated_at.desc()).limit(limit))).scalars().all()
    return list(rows)


async def analyze_writing_style(
    db: AsyncSession,
    *,
    owner_user_id: int,
    question: str,
    author_or_journal: str | None = None,
    entry_ids: list[str] | None = None,
    section_type: str | None = None,
    limit_entries: int = 5,
    max_sections_per_entry: int = 6,
) -> dict[str, Any]:
    style_focus = section_type if section_type in {"introduction", "theory", "method", "general"} else detect_style_focus(question)
    entries = await select_style_entries(
        db,
        owner_user_id=owner_user_id,
        question=question,
        author_or_journal=author_or_journal,
        entry_ids=entry_ids,
        limit_entries=limit_entries,
    )
    evidence: list[dict[str, Any]] = []
    limitations = ["未联网；仅检索本地文献库中已绑定的 Markdown 原文。"]

    for entry in entries:
        file_id = entry.markdown_source_file_id or entry.source_file_id
        file_record = await db.get(File, file_id) if file_id else None
        if not file_record or file_record.owner_user_id != owner_user_id:
            limitations.append(f"{entry.title}: 未绑定可检索原文文件")
            continue
        if file_record.file_type != "markdown":
            limitations.append(f"{entry.title}: 当前仅从 Markdown 原文抽取写作风格片段")
            continue
        path = resolve_storage_path(file_record.storage_path)
        if not path.exists() or not path.is_file():
            limitations.append(f"{entry.title}: Markdown 原文文件不存在")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for section in extract_style_sections(text, style_focus, max_sections_per_entry):
            evidence.append(
                {
                    "entry_id": entry.id,
                    "title": entry.title,
                    "source_tier": "P0",
                    "source_kind": "style_evidence",
                    "file_id": file_record.id,
                    "file_name": file_record.original_name,
                    **section,
                }
            )

    if entries and not evidence:
        limitations.append("匹配文献没有可用的原文分节片段，不能声称已分析原文写法。")
    if not entries:
        limitations.append("未在当前用户文献库中找到匹配的作者、期刊、标题或 entry_id。")

    return {
        "question": question,
        "style_focus": style_focus,
        "entries": [_entry_summary(entry) for entry in entries],
        "style_evidence": evidence,
        "analysis_instructions": [
            "只基于 style_evidence 中的原文片段分析写法，不要虚构原文。",
            "区分可直接从原文观察到的写作特征和你的解释性概括。",
            "如证据不足，明确说明缺口，并建议补充对应章节原文。",
        ],
        "limitations": limitations,
    }
