from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from prompt_registry import get_builtin_fallback, load_prompt_from_file
from prompt_service import get_effective_prompt_text


@dataclass(frozen=True, slots=True)
class JournalTierMatch:
    tier: str
    label: str
    matched_name: str


@dataclass(frozen=True, slots=True)
class JournalTierDefinition:
    tier: str
    label: str
    names: list[str]
    score: float


@dataclass(frozen=True, slots=True)
class JournalQualityMatcher:
    definitions: list[JournalTierDefinition]
    normalized_index: list[tuple[str, str, str, bool]]
    labels: dict[str, str]
    scores: dict[str, float]


_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "economics_top5": ("economics top 5", "econ top 5", "经济学 top 5"),
    "management_utd24_selected": ("management utd 24", "management utd 24 selected", "utd 24", "管理 utd 24", "management top"),
    "finance_top3": ("finance top 3", "金融 top 3"),
    "chinese_top_tier": ("chinese top tier", "中文顶刊", "国内顶刊", "中文 top tier"),
    "general_science": ("general science", "综合科学"),
}

_LABEL_TO_TIER: dict[str, str] = {}
for _tier_key, _aliases in _LABEL_ALIASES.items():
    for _alias in _aliases:
        _LABEL_TO_TIER[_alias] = _tier_key

_DEFAULT_TIER_SCORES = {
    "economics_top5": 1.0,
    "management_utd24_selected": 0.96,
    "finance_top3": 0.98,
    "chinese_top_tier": 0.94,
    "general_science": 0.92,
}


def _normalize_journal_name(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = re.sub(r"[\u3000\s]+", " ", text)
    text = re.sub(r"[()（）\[\]{}.,:;!?'\"`·\-_/]+", "", text)
    return text


def _normalize_label(value: str | None) -> str:
    return _normalize_journal_name(value)


def _fallback_score_for_label(label: str, index: int) -> float:
    tier = _LABEL_TO_TIER.get(_normalize_label(label))
    if tier:
        return _DEFAULT_TIER_SCORES.get(tier, 0.9)
    return max(0.6, 0.9 - index * 0.03)


def _slugify_label(label: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", _normalize_label(label))
    return base.strip("_") or "custom_tier"


def _allows_fuzzy_match(original: str, normalized: str) -> bool:
    if not normalized:
        return False
    if re.search(r"[\u4e00-\u9fff]", original):
        return True
    return " " in normalized


def parse_journal_kb_text(content: str | None) -> list[JournalTierDefinition]:
    definitions: list[JournalTierDefinition] = []
    text = str(content or "")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = re.match(r"^-\s+\*\*(.+?)\*\*\s*:\s*(.+)$", line)
        if not match:
            continue
        label = match.group(1).strip()
        names_text = match.group(2).strip()
        names = [item.strip() for item in names_text.split(",") if item.strip()]
        if not label or not names:
            continue
        tier = _LABEL_TO_TIER.get(_normalize_label(label), _slugify_label(label))
        definitions.append(
            JournalTierDefinition(
                tier=tier,
                label=label,
                names=names,
                score=_fallback_score_for_label(label, len(definitions)),
            )
        )
    return definitions


def build_journal_quality_matcher(content: str | None) -> JournalQualityMatcher:
    definitions = parse_journal_kb_text(content)
    normalized_index: list[tuple[str, str, str, bool]] = []
    labels: dict[str, str] = {}
    scores: dict[str, float] = {}
    for definition in definitions:
        labels[definition.tier] = definition.label
        scores[definition.tier] = definition.score
        for name in definition.names:
            normalized = _normalize_journal_name(name)
            if normalized:
                normalized_index.append(
                    (
                        normalized,
                        definition.tier,
                        name,
                        _allows_fuzzy_match(name, normalized),
                    )
                )
    return JournalQualityMatcher(
        definitions=definitions,
        normalized_index=normalized_index,
        labels=labels,
        scores=scores,
    )


def default_journal_kb_text() -> str:
    return load_prompt_from_file("journal_kb", "top_tier_registry") or get_builtin_fallback(
        "journal_kb", "top_tier_registry"
    )


_DEFAULT_MATCHER = build_journal_quality_matcher(default_journal_kb_text())


def lookup_journal_tier_with_matcher(
    matcher: JournalQualityMatcher,
    journal_name: str | None,
) -> JournalTierMatch | None:
    normalized = _normalize_journal_name(journal_name)
    if not normalized:
        return None
    for candidate, tier, original, _allow_fuzzy in matcher.normalized_index:
        if normalized == candidate:
            return JournalTierMatch(tier=tier, label=matcher.labels[tier], matched_name=original)
    for candidate, tier, original, allow_fuzzy in matcher.normalized_index:
        if allow_fuzzy and candidate and (candidate in normalized or normalized in candidate):
            return JournalTierMatch(tier=tier, label=matcher.labels[tier], matched_name=original)
    return None


def lookup_journal_tier(journal_name: str | None) -> JournalTierMatch | None:
    return lookup_journal_tier_with_matcher(_DEFAULT_MATCHER, journal_name)


def score_journal_quality_with_matcher(
    matcher: JournalQualityMatcher,
    journal_name: str | None,
) -> tuple[float, dict[str, str] | None]:
    match = lookup_journal_tier_with_matcher(matcher, journal_name)
    if not match:
        return 0.0, None
    return matcher.scores.get(match.tier, 0.0), {
        "tier": match.tier,
        "label": match.label,
        "matched_name": match.matched_name,
    }


def score_journal_quality(journal_name: str | None) -> tuple[float, dict[str, str] | None]:
    return score_journal_quality_with_matcher(_DEFAULT_MATCHER, journal_name)


async def build_prompt_journal_quality_matcher(
    db: AsyncSession,
    *,
    user_id: int,
) -> JournalQualityMatcher:
    content = await get_effective_prompt_text(
        db,
        user_id=user_id,
        prompt_type="journal_kb",
        prompt_key="top_tier_registry",
    )
    return build_journal_quality_matcher(content)


def make_journal_scorer(
    matcher: JournalQualityMatcher,
) -> Callable[[str | None], tuple[float, dict[str, str] | None]]:
    return lambda journal_name: score_journal_quality_with_matcher(matcher, journal_name)
