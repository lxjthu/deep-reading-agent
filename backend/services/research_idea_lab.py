"""Economics/management research idea helpers built on local evidence packs."""
from __future__ import annotations

import re
from typing import Any


ECON_MANAGEMENT_HINTS = {
    "mechanism": ("mechanism", "through", "mediate", "mediator", "路径", "机制", "中介"),
    "moderator": ("moderate", "moderator", "contingent", "边界", "调节"),
    "identification": ("did", "iv", "fixed effects", "instrument", "识别", "内生性", "固定效应"),
    "data": ("data", "sample", "panel", "dataset", "样本", "数据"),
}


def _compact(value: str | None) -> str:
    return " ".join((value or "").split())


def _tokenize(text: str) -> list[str]:
    return [part.lower() for part in re.findall(r"[A-Za-z][A-Za-z-]{2,}|[\u4e00-\u9fff]{2,}", text or "")]


def _entry_evidence(entry: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = entry.get("evidence") or entry.get("items") or []
    rows: list[dict[str, Any]] = []
    for row in evidence:
        text = _compact(row.get("text") or row.get("quote") or row.get("content"))
        if not text:
            continue
        rows.append(
            {
                "entry_id": str(entry.get("entry_id") or entry.get("id") or ""),
                "title": _compact(entry.get("title")),
                "source_tier": row.get("source_tier") or "P2",
                "source_kind": row.get("source_kind") or "unknown",
                "quote": text[:700],
            }
        )
    return rows


def _infer_construct_name(topic: str, text: str) -> str:
    topic_terms = _tokenize(topic)
    text_terms = _tokenize(text)
    for term in topic_terms:
        if term in text_terms:
            return term
    return text_terms[0] if text_terms else "research construct"


def _extract_hint_phrases(text: str, hint_type: str) -> list[str]:
    lowered = text.lower()
    hits = [hint for hint in ECON_MANAGEMENT_HINTS[hint_type] if hint.lower() in lowered]
    return hits[:5]


def extract_constructs_from_evidence(
    *,
    evidence_pack: dict[str, Any],
    topic: str,
    max_constructs: int = 8,
) -> dict[str, Any]:
    """Extract lightweight construct notes from an existing evidence pack."""
    entries = evidence_pack.get("entries") or []
    constructs: list[dict[str, Any]] = []
    limitations: list[str] = []

    for entry in entries:
        rows = _entry_evidence(entry)
        if not rows:
            limitations.append(f"{entry.get('title') or entry.get('entry_id')}: no usable evidence snippets")
            continue
        combined = " ".join(row["quote"] for row in rows)
        name = _infer_construct_name(topic, combined)
        constructs.append(
            {
                "construct_id": f"construct_{len(constructs) + 1}",
                "name": name,
                "category": "construct",
                "definition": combined[:500],
                "mechanisms": _extract_hint_phrases(combined, "mechanism"),
                "variables": {"independent": [], "dependent": [], "mediators": [], "moderators": []},
                "empirical_design": {
                    "data_sources": _extract_hint_phrases(combined, "data"),
                    "identification": _extract_hint_phrases(combined, "identification"),
                    "risks": [],
                },
                "evidence": rows[:5],
                "uncertainty": "medium",
            }
        )
        if len(constructs) >= max(1, max_constructs):
            break

    return {
        "status": "ready",
        "topic": topic,
        "constructs": constructs,
        "limitations": limitations,
    }
