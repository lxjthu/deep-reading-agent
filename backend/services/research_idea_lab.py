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

def diagnose_research_gaps(*, construct_result: dict[str, Any], topic: str) -> dict[str, Any]:
    """Diagnose conservative evidence gaps from construct notes."""
    gaps: list[dict[str, Any]] = []
    for construct in construct_result.get("constructs") or []:
        evidence = construct.get("evidence") or []
        empirical = construct.get("empirical_design") or {}
        if not empirical.get("identification"):
            gaps.append(
                {
                    "gap_id": f"gap_{len(gaps) + 1}",
                    "gap_type": "causal_identification",
                    "summary": f"{construct.get('name')}: causal identification is not yet explicit in the retrieved evidence.",
                    "why_it_matters": "Economics and management claims need a credible design before the idea can become a research plan.",
                    "supporting_evidence": evidence[:3],
                    "needed_evidence": ["identification strategy evidence", "data source and variation source"],
                    "confidence": "medium",
                }
            )
        if construct.get("mechanisms") == []:
            gaps.append(
                {
                    "gap_id": f"gap_{len(gaps) + 1}",
                    "gap_type": "mechanism",
                    "summary": f"{construct.get('name')}: mechanism chain is weak or absent.",
                    "why_it_matters": "A clear mechanism supports theory contribution and testable hypotheses.",
                    "supporting_evidence": evidence[:3],
                    "needed_evidence": ["mechanism evidence", "mediator or moderator discussion"],
                    "confidence": "medium",
                }
            )
    return {"status": "ready", "topic": topic, "gaps": gaps, "limitations": construct_result.get("limitations") or []}


def generate_research_ideas(
    *,
    construct_result: dict[str, Any],
    gap_result: dict[str, Any],
    max_ideas: int = 5,
) -> dict[str, Any]:
    """Generate structured economics/management idea candidates from constructs and gaps."""
    constructs = construct_result.get("constructs") or []
    gaps = gap_result.get("gaps") or []
    ideas: list[dict[str, Any]] = []

    for construct in constructs[: max(1, max_ideas)]:
        name = construct.get("name") or "research construct"
        evidence_refs: list[str] = []
        for row in construct.get("evidence") or []:
            entry_id = row.get("entry_id")
            if entry_id and entry_id not in evidence_refs:
                evidence_refs.append(entry_id)
        related_gap = gaps[0] if gaps else {}
        ideas.append(
            {
                "idea_id": f"idea_{len(ideas) + 1}",
                "title": f"How does {name} shape economic or management outcomes?",
                "research_question": f"How does {name} affect the focal outcome, and through which mechanism?",
                "theory_base": [],
                "mechanism_chain": [name] + list(construct.get("mechanisms") or []),
                "hypotheses": [
                    f"H1: {name} is associated with the focal economic or management outcome.",
                    "H2: The relationship operates through the mechanism identified in the evidence set.",
                ],
                "data_strategy": {
                    "sample": "",
                    "variables": [name],
                    "identification": "Use the evidence gaps to choose fixed effects, DID, IV, or another credible design.",
                },
                "contribution": ["theory contribution", "empirical design contribution"],
                "risks": [related_gap.get("summary")] if related_gap else [],
                "evidence_refs": evidence_refs,
                "confidence": "medium" if evidence_refs else "low",
            }
        )

    return {"status": "ready", "topic": construct_result.get("topic") or "", "ideas": ideas, "gaps": gaps}

def run_idea_lab_pipeline(
    *,
    evidence_pack: dict[str, Any],
    topic: str,
    max_constructs: int = 8,
    max_ideas: int = 5,
) -> dict[str, Any]:
    construct_result = extract_constructs_from_evidence(
        evidence_pack=evidence_pack,
        topic=topic,
        max_constructs=max_constructs,
    )
    gap_result = diagnose_research_gaps(construct_result=construct_result, topic=topic)
    idea_result = generate_research_ideas(
        construct_result=construct_result,
        gap_result=gap_result,
        max_ideas=max_ideas,
    )
    return {
        "status": "ready",
        "topic": topic,
        "constructs": construct_result.get("constructs") or [],
        "gaps": gap_result.get("gaps") or [],
        "ideas": idea_result.get("ideas") or [],
        "limitations": construct_result.get("limitations") or [],
    }

