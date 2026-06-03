from __future__ import annotations

from typing import Any


TIERS = ("P0", "P1", "P2", "P3")


def assess_evidence_sufficiency(
    evidence_pack: dict[str, Any],
    *,
    user_requested_external: bool,
) -> dict[str, Any]:
    tier_summary = {tier: 0 for tier in TIERS}

    for entry in evidence_pack.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        for evidence in entry.get("evidence") or []:
            if not isinstance(evidence, dict):
                continue
            tier = str(evidence.get("source_tier") or "").upper()
            if tier in tier_summary:
                tier_summary[tier] += 1

    evidence_count = sum(tier_summary.values())
    has_authoritative = bool(tier_summary["P0"] or tier_summary["P1"])
    has_ai_only = bool(tier_summary["P2"] and not has_authoritative)
    has_external_only = bool(tier_summary["P3"] and not has_authoritative and not tier_summary["P2"])

    if user_requested_external and (evidence_count == 0 or has_ai_only):
        return {
            "status": "needs_external_consent",
            "can_answer": False,
            "needs_external_consent": True,
            "evidence_count": evidence_count,
            "tier_summary": tier_summary,
            "message": "Local evidence is weak for this externally scoped request. Ask for explicit external retrieval consent before answering.",
        }

    if has_authoritative:
        return {
            "status": "sufficient",
            "can_answer": True,
            "needs_external_consent": False,
            "evidence_count": evidence_count,
            "tier_summary": tier_summary,
            "message": "Evidence includes P0/P1 material and is sufficient for a local-first answer.",
        }

    if has_ai_only:
        return {
            "status": "p2_only",
            "can_answer": True,
            "needs_external_consent": False,
            "evidence_count": evidence_count,
            "tier_summary": tier_summary,
            "message": "Current support is based only on AI notes. Answer with an explicit AI-evidence warning.",
        }

    if has_external_only:
        return {
            "status": "external_only",
            "can_answer": True,
            "needs_external_consent": False,
            "evidence_count": evidence_count,
            "tier_summary": tier_summary,
            "message": "Evidence is external and temporary. Mark it as P3 and avoid persisting it automatically.",
        }

    return {
        "status": "insufficient",
        "can_answer": False,
        "needs_external_consent": False,
        "evidence_count": 0,
        "tier_summary": tier_summary,
        "message": "No local evidence was found. Ask a clarifying question or run local retrieval again with a narrower scope.",
    }
