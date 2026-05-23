from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from db.models import BibEntry, CardNote
from result_storage import build_result_storage_path, get_results_root, resolve_result_path
from upload_storage import resolve_storage_path


FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n?", re.DOTALL)


def json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def slugify(value: str, *, fallback: str = "note") -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip().lower(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return (text or fallback)[:80]


def strip_frontmatter(markdown: str) -> str:
    return FRONTMATTER_RE.sub("", markdown or "").lstrip()


def read_markdown_file(storage_path: str) -> str:
    path = resolve_storage_path(storage_path)
    return path.read_text(encoding="utf-8")


def read_artifact_markdown(storage_path: str) -> str:
    path = resolve_result_path(storage_path)
    return path.read_text(encoding="utf-8")


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str) and not value.strip():
        return "null"
    return json.dumps(str(value), ensure_ascii=False)


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(json.dumps(str(value), ensure_ascii=False) for value in values) + "]"


def paper_note_basename(entry: BibEntry, version: str) -> str:
    return f"paper-{entry.id}-{version}"


def card_note_basename(card: CardNote) -> str:
    return f"card-{card.id}-{slugify(card.title, fallback='card')}"


def build_paper_markdown(
    entry: BibEntry,
    *,
    version: str,
    content: str,
    cards: list[CardNote] | None = None,
) -> str:
    authors = json_list(entry.authors_json)
    keywords = json_list(entry.keywords_json)
    card_lines: list[str] = []
    for card in cards or []:
        if card.source_version != version:
            continue
        card_lines.append(f"- [[{card_note_basename(card)}|{card.title}]]")

    frontmatter = [
        "---",
        f"paper_id: {yaml_scalar(entry.id)}",
        f"title: {yaml_scalar(entry.title)}",
        f"authors: {yaml_list(authors)}",
        f"journal: {yaml_scalar(entry.journal)}",
        f"year: {entry.year if entry.year is not None else 'null'}",
        f"volume: {yaml_scalar(entry.volume)}",
        f"issue: {yaml_scalar(entry.issue)}",
        f"pages: {yaml_scalar(entry.pages)}",
        f"doi: {yaml_scalar(entry.doi)}",
        f"keywords: {yaml_list(keywords)}",
        f"version: {yaml_scalar(version)}",
        "---",
        "",
    ]
    abstract = entry.abstract or ""
    if abstract:
        frontmatter.extend(["## 摘要", "", abstract.strip(), ""])
    if card_lines:
        frontmatter.extend(["## 关联卡片", "", *card_lines, ""])
    frontmatter.extend(["## 正文", "", strip_frontmatter(content).strip(), ""])
    return "\n".join(frontmatter)


def build_card_markdown(card: CardNote, entry: BibEntry) -> str:
    tags = json_list(card.tags_json)
    authors = json_list(entry.authors_json)
    paper_base = paper_note_basename(entry, card.source_version)
    frontmatter = [
        "---",
        f"card_id: {yaml_scalar(card.id)}",
        f"title: {yaml_scalar(card.title)}",
        f"source_paper_id: {yaml_scalar(entry.id)}",
        f"source_title: {yaml_scalar(entry.title)}",
        f"authors: {yaml_list(authors)}",
        f"journal: {yaml_scalar(entry.journal)}",
        f"year: {entry.year if entry.year is not None else 'null'}",
        f"volume: {yaml_scalar(entry.volume)}",
        f"issue: {yaml_scalar(entry.issue)}",
        f"pages: {yaml_scalar(entry.pages)}",
        f"doi: {yaml_scalar(entry.doi)}",
        f"source_version: {yaml_scalar(card.source_version)}",
        f"source_paper: {yaml_scalar(f'[[{paper_base}|{entry.title}]]')}",
        f"created_at: {yaml_scalar(card.created_at.isoformat() if card.created_at else '')}",
        f"tags: {yaml_list(tags)}",
        f"summary: {yaml_scalar(card.summary)}",
        "---",
        "",
        f"# {card.title}",
        "",
    ]
    if card.summary:
        frontmatter.extend([card.summary.strip(), ""])
    frontmatter.extend([
        card.body_markdown.strip(),
        "",
        "## 来源摘录",
        "",
        f"> {card.selected_text.strip().replace(chr(10), chr(10) + '> ')}",
        "",
        "## 来源论文",
        "",
        f"- [[{paper_base}|{entry.title}]]",
        "",
    ])
    return "\n".join(frontmatter)


def write_card_mirror(card: CardNote, entry: BibEntry) -> str:
    root = get_results_root() / str(card.owner_user_id) / "notes" / "cards"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{card_note_basename(card)}.md"
    path.write_text(build_card_markdown(card, entry), encoding="utf-8")
    return build_result_storage_path(path)


def delete_card_mirror(storage_path: str | None) -> None:
    if not storage_path:
        return
    path = resolve_result_path(storage_path)
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except FileNotFoundError:
        pass
