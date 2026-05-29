from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, UTC
import math
import re
from typing import Any, Awaitable, Callable
import uuid

from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import BibEntry
from services.journal_quality_kb import (
    build_prompt_journal_quality_matcher,
    make_journal_scorer,
    score_journal_quality,
)


ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

BATCH_SIZE_DEFAULT = 100
MAX_PRIORITY_ITEMS = 20

_EN_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "using", "based", "study", "studies", "paper",
    "evidence", "analysis", "effects", "effect", "impact", "role", "model", "models", "data",
    "research", "approach", "case", "cases", "review", "reviews", "empirical", "china", "chinese",
}
_ZH_STOPWORDS = {"研究", "基于", "中国", "企业", "影响", "机制", "视角", "效应", "分析", "实证", "文献", "综述"}

_SOURCE_WEIGHTS = {
    "keywords_tags": 3.0,
    "title": 2.0,
    "abstract": 1.0,
}

_TOPIC_RULES: list[dict[str, Any]] = [
    {
        "label": "大语言模型 / ChatGPT",
        "aliases": ["chatgpt", "gpt-4", "gpt4", "large language model", "large language models", "llm", "llms", "foundation model", "foundation models"],
        "priority": 1.7,
    },
    {
        "label": "生成式人工智能 / GenAI",
        "aliases": ["generative ai", "generative artificial intelligence", "genai", "aigc", "生成式人工智能", "生成式ai"],
        "priority": 1.6,
    },
    {
        "label": "人工智能应用（通用）",
        "aliases": ["artificial intelligence", "machine learning", "deep learning", "neural network", "ai adoption", "ai capability", "人工智能", "机器学习", "深度学习"],
        "priority": 1.0,
    },
    {
        "label": "数字化转型",
        "aliases": ["digital transformation", "digitalization", "digitization", "数字化转型", "数智化", "数字化"],
        "priority": 1.2,
    },
    {
        "label": "创新与技术采纳",
        "aliases": ["technology adoption", "innovation", "innovation performance", "technology acceptance", "diffusion", "创新", "技术采纳", "技术接受"],
        "priority": 1.1,
    },
    {
        "label": "平台与生态系统",
        "aliases": ["platform", "ecosystem", "complementor", "two-sided market", "digital platform", "平台", "生态系统", "双边市场"],
        "priority": 1.15,
    },
    {
        "label": "公司治理与战略管理",
        "aliases": ["corporate governance", "strategy", "strategic management", "board", "upper echelons", "governance", "公司治理", "战略管理", "董事会"],
        "priority": 1.15,
    },
    {
        "label": "营销与消费者行为",
        "aliases": ["marketing", "consumer", "brand", "advertising", "customer", "retail", "营销", "消费者", "品牌", "广告", "零售"],
        "priority": 1.15,
    },
    {
        "label": "金融与资本市场",
        "aliases": ["finance", "bank", "banking", "stock", "capital market", "investment", "asset pricing", "fintech", "金融", "银行", "资本市场", "投资"],
        "priority": 1.15,
    },
    {
        "label": "会计与审计",
        "aliases": ["accounting", "audit", "auditing", "earnings management", "disclosure", "会计", "审计", "信息披露"],
        "priority": 1.1,
    },
    {
        "label": "运营与供应链",
        "aliases": ["operations", "supply chain", "logistics", "inventory", "manufacturing", "运营管理", "供应链", "物流", "制造"],
        "priority": 1.15,
    },
    {
        "label": "组织行为与人力资源",
        "aliases": ["organizational behavior", "human resource", "employee", "leadership", "team", "job performance", "组织行为", "人力资源", "员工", "领导力", "团队"],
        "priority": 1.1,
    },
    {
        "label": "创业与中小企业",
        "aliases": ["entrepreneurship", "startup", "start-up", "sme", "small business", "创业", "中小企业", "初创企业"],
        "priority": 1.1,
    },
    {
        "label": "ESG / 可持续发展",
        "aliases": ["esg", "sustainability", "sustainable", "csr", "environmental social governance", "可持续", "绿色创新", "社会责任"],
        "priority": 1.1,
    },
    {
        "label": "气候变化与环境",
        "aliases": ["climate change", "global warming", "carbon", "emission", "biodiversity", "environmental", "气候变化", "碳排放", "环境"],
        "priority": 1.15,
    },
    {
        "label": "农业与作物科学",
        "aliases": ["agriculture", "crop", "rice", "wheat", "maize", "pest", "agricultural", "农业", "作物", "水稻", "小麦", "玉米", "病虫害"],
        "priority": 1.1,
    },
    {
        "label": "教育与学习",
        "aliases": ["education", "learning", "teaching", "student", "classroom", "教育", "学习", "教学", "学生"],
        "priority": 1.05,
    },
    {
        "label": "医疗与健康",
        "aliases": ["health", "healthcare", "medical", "hospital", "patient", "medicine", "健康", "医疗", "医院", "患者"],
        "priority": 1.05,
    },
]

_PREFERRED_GENERALIZATION = {
    "large language model": "大语言模型 / ChatGPT",
    "llm": "大语言模型 / ChatGPT",
    "llms": "大语言模型 / ChatGPT",
    "chatgpt": "大语言模型 / ChatGPT",
    "gpt4": "大语言模型 / ChatGPT",
    "gpt-4": "大语言模型 / ChatGPT",
    "generative ai": "生成式人工智能 / GenAI",
    "generative artificial intelligence": "生成式人工智能 / GenAI",
    "genai": "生成式人工智能 / GenAI",
    "aigc": "生成式人工智能 / GenAI",
    "artificial intelligence": "人工智能应用（通用）",
    "machine learning": "人工智能应用（通用）",
    "deep learning": "人工智能应用（通用）",
    "climate change": "气候变化与环境",
    "climatechange": "气候变化与环境",
}


@dataclass(slots=True)
class CandidateRecord:
    entry_id: str
    title: str
    journal: str
    year: int | None
    citation_count: int | None
    reading_status: str
    metadata_completeness: str
    has_fulltext: bool
    keywords: list[str]
    tags: list[str]
    abstract: str


def _json_list(raw: str | None) -> list[str]:
    import json

    try:
        value = json.loads(raw or "[]")
    except Exception:
        return []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _entry_to_record(entry: BibEntry) -> CandidateRecord:
    return CandidateRecord(
        entry_id=entry.id,
        title=entry.title or "",
        journal=entry.journal or "",
        year=entry.year,
        citation_count=entry.citation_count,
        reading_status=entry.reading_status,
        metadata_completeness=entry.metadata_completeness,
        has_fulltext=bool(entry.source_file_id or entry.markdown_source_file_id),
        keywords=_json_list(entry.keywords_json),
        tags=_json_list(entry.user_tags_json),
        abstract=(entry.abstract or "")[:1200],
    )


def _extract_terms(record: CandidateRecord) -> list[str]:
    preferred = [item for item in [*record.tags, *record.keywords] if item]
    if preferred:
        return preferred[:6]
    text = " ".join([record.title, record.abstract])
    zh_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    en_terms = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
    combined = [
        term for term in [*zh_terms, *en_terms]
        if term not in _ZH_STOPWORDS and term not in _EN_STOPWORDS
    ]
    return combined[:8]


def _normalize_topic_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = text.replace("chat gpt", "chatgpt")
    text = re.sub(r"[\u3000\s]+", " ", text)
    text = re.sub(r"[()（）\[\]{}.,:;!?\"'`·/_]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_topic_token(value: str | None) -> str:
    text = _normalize_topic_text(value)
    return text.replace(" ", "")


def _text_sources(record: CandidateRecord) -> dict[str, str]:
    return {
        "keywords_tags": " ".join([*record.tags, *record.keywords]),
        "title": record.title,
        "abstract": record.abstract,
    }


def _fallback_cluster_label(record: CandidateRecord) -> str:
    terms = _extract_terms(record)
    for term in terms:
        token = _normalize_topic_token(term)
        if token in _PREFERRED_GENERALIZATION:
            return _PREFERRED_GENERALIZATION[token]
        normalized = _normalize_topic_text(term)
        if normalized in _PREFERRED_GENERALIZATION:
            return _PREFERRED_GENERALIZATION[normalized]
        if re.search(r"[\u4e00-\u9fff]", term):
            return term[:10]
        if normalized:
            return " ".join(part.capitalize() for part in normalized.split()[:3])
    if record.journal:
        return record.journal[:30]
    return "长尾交叉主题"


def _cluster_key(record: CandidateRecord) -> str:
    source_texts = _text_sources(record)
    scores: Counter[str] = Counter()
    matched_specific_ai = False
    for rule in _TOPIC_RULES:
        label = str(rule["label"])
        aliases = [str(alias) for alias in rule.get("aliases") or []]
        priority = float(rule.get("priority") or 1.0)
        for source_name, raw_text in source_texts.items():
            normalized_source = _normalize_topic_text(raw_text)
            compact_source = _normalize_topic_token(raw_text)
            if not normalized_source and not compact_source:
                continue
            for alias in aliases:
                normalized_alias = _normalize_topic_text(alias)
                compact_alias = _normalize_topic_token(alias)
                if not normalized_alias and not compact_alias:
                    continue
                if (normalized_alias and normalized_alias in normalized_source) or (
                    compact_alias and compact_alias in compact_source
                ):
                    base = _SOURCE_WEIGHTS.get(source_name, 1.0) * priority
                    length_bonus = min(len(normalized_alias.replace(" ", "")) / 18.0, 1.0)
                    scores[label] += base + length_bonus
                    if label in {"大语言模型 / ChatGPT", "生成式人工智能 / GenAI"}:
                        matched_specific_ai = True

    if matched_specific_ai and "人工智能应用（通用）" in scores:
        scores["人工智能应用（通用）"] *= 0.35

    if scores:
        best_score = max(scores.values())
        candidates = [label for label, score in scores.items() if score == best_score]
        candidates.sort(key=lambda item: (-len(item), item))
        return candidates[0]

    return _fallback_cluster_label(record)


def _metadata_score(record: CandidateRecord) -> float:
    score = 0.0
    if record.metadata_completeness == "full":
        score += 1.0
    elif record.metadata_completeness == "partial":
        score += 0.6
    else:
        score += 0.2
    if record.has_fulltext:
        score += 1.0
    if record.abstract:
        score += 0.6
    return score


def _citation_score(value: int | None) -> float:
    if value is None or value <= 0:
        return 0.0
    return min(math.log10(value + 1), 2.0)


def _recency_score(year: int | None) -> float:
    if not year:
        return 0.0
    if year >= 2024:
        return 1.0
    if year >= 2021:
        return 0.8
    if year >= 2018:
        return 0.5
    return 0.2


def _priority_score(
    record: CandidateRecord,
    *,
    journal_scorer: Callable[[str | None], tuple[float, dict[str, str] | None]] = score_journal_quality,
) -> tuple[float, dict[str, Any]]:
    journal_score, journal_match = journal_scorer(record.journal)
    score = (
        0.45 * journal_score
        + 0.2 * _metadata_score(record)
        + 0.2 * _citation_score(record.citation_count)
        + 0.15 * _recency_score(record.year)
    )
    reasons: list[str] = []
    if journal_match:
        reasons.append(f"命中高质量期刊名录：{journal_match['label']}")
    if record.has_fulltext:
        reasons.append("已有可用全文")
    if record.metadata_completeness == "full":
        reasons.append("元数据完整")
    if record.citation_count and record.citation_count > 0:
        reasons.append(f"被引 {record.citation_count} 次")
    if record.year:
        reasons.append(f"{record.year} 年发表")
    return round(score, 4), {
        "journal_quality": journal_match,
        "reasons": reasons,
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _annotated_entry(
    record: CandidateRecord,
    *,
    cluster_label: str,
    score: float,
    detail: dict[str, Any],
) -> dict[str, Any]:
    return {
        "entry_id": record.entry_id,
        "title": record.title,
        "journal": record.journal,
        "year": record.year,
        "citation_count": record.citation_count,
        "reading_status": record.reading_status,
        "metadata_completeness": record.metadata_completeness,
        "has_fulltext": record.has_fulltext,
        "priority_score": score,
        "cluster_labels": [cluster_label] if cluster_label else [],
        "local_rule_reasons": detail.get("reasons") or [],
        "journal_quality": detail.get("journal_quality"),
    }


def _merge_counter(target: Counter[str], source: Counter[str]) -> None:
    for key, value in source.items():
        target[key] += value


def _build_batch_note(
    *,
    topic: str,
    batch_index: int,
    batch_size: int,
    processed_count: int,
    total_count: int,
    cluster_counter: Counter[str],
    journal_counter: Counter[str],
    priority_records: list[tuple[float, CandidateRecord, dict[str, Any]]],
) -> dict[str, Any]:
    top_clusters = [
        {"label": label, "count": count}
        for label, count in cluster_counter.most_common(5)
    ]
    top_journals = [
        {"label": label, "count": count}
        for label, count in journal_counter.most_common(5)
    ]
    candidates = []
    for score, record, detail in sorted(priority_records, key=lambda item: item[0], reverse=True)[:5]:
        candidates.append(
            {
                "entry_id": record.entry_id,
                "title": record.title,
                "journal": record.journal,
                "year": record.year,
                "priority_score": score,
                "reasons": detail.get("reasons") or [],
                "journal_quality": detail.get("journal_quality"),
            }
        )
    cluster_text = "、".join(item["label"] for item in top_clusters[:3]) or "暂无明显主题"
    return {
        "kind": "batch_analysis",
        "topic": topic,
        "batch_index": batch_index,
        "batch_size": batch_size,
        "processed_count": processed_count,
        "total_count": total_count,
        "summary": f"已处理 {processed_count}/{total_count} 篇，当前批次主要聚焦在：{cluster_text}。",
        "top_clusters": top_clusters,
        "journal_tier_counts": top_journals,
        "priority_candidates": candidates,
    }


def _aggregate_final_summary(
    *,
    topic: str,
    total_count: int,
    cluster_counter: Counter[str],
    tier_counter: Counter[str],
    ranked_records: list[tuple[float, CandidateRecord, dict[str, Any]]],
) -> dict[str, Any]:
    most_common_clusters = cluster_counter.most_common()
    final_clusters = [
        {"label": label, "count": count}
        for label, count in most_common_clusters[:12]
    ]
    long_tail_clusters = [
        {"label": label, "count": count}
        for label, count in most_common_clusters[12:20]
    ]
    long_tail_count = sum(count for _, count in most_common_clusters[12:])
    top_candidates = []
    for score, record, detail in sorted(ranked_records, key=lambda item: item[0], reverse=True)[:MAX_PRIORITY_ITEMS]:
        top_candidates.append(
            {
                "entry_id": record.entry_id,
                "title": record.title,
                "journal": record.journal,
                "year": record.year,
                "citation_count": record.citation_count,
                "priority_score": score,
                "local_rule_reasons": detail.get("reasons") or [],
                "journal_quality": detail.get("journal_quality"),
                "model_hint": "可由大模型基于题名、摘要与主题关系补充判读，但不得覆盖本地名录命中结果。",
            }
        )
    return {
        "topic": topic,
        "count": total_count,
        "clusters": final_clusters,
        "long_tail_clusters": long_tail_clusters,
        "long_tail_count": long_tail_count,
        "journal_tier_distribution": [
            {"label": label, "count": count}
            for label, count in tier_counter.most_common(8)
        ],
        "priority_candidates": top_candidates,
        "table_columns": [
            "title",
            "journal",
            "year",
            "citation_count",
            "priority_score",
            "local_rule_reasons",
            "journal_quality",
            "model_hint",
        ],
    }


def _aggregate_summary_from_dataset_entries(topic: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    cluster_counter: Counter[str] = Counter()
    tier_counter: Counter[str] = Counter()
    for item in entries:
        if not isinstance(item, dict):
            continue
        for label in item.get("cluster_labels") or []:
            if label:
                cluster_counter[str(label)] += 1
        journal_quality = item.get("journal_quality") or {}
        label = str(journal_quality.get("label") or "")
        if label:
            tier_counter[label] += 1
    most_common_clusters = cluster_counter.most_common()
    sorted_entries = sorted(
        [item for item in entries if isinstance(item, dict)],
        key=lambda item: float(item.get("priority_score") or 0.0),
        reverse=True,
    )
    return {
        "topic": topic,
        "count": len(entries),
        "clusters": [{"label": label, "count": count} for label, count in most_common_clusters[:12]],
        "long_tail_clusters": [{"label": label, "count": count} for label, count in most_common_clusters[12:20]],
        "long_tail_count": sum(count for _, count in most_common_clusters[12:]),
        "journal_tier_distribution": [{"label": label, "count": count} for label, count in tier_counter.most_common(8)],
        "priority_candidates": sorted_entries[:MAX_PRIORITY_ITEMS],
        "table_columns": [
            "title",
            "journal",
            "year",
            "citation_count",
            "priority_score",
            "local_rule_reasons",
            "journal_quality",
        ],
    }


def _build_analysis_cache(
    *,
    topic: str,
    query: str,
    reading_status: str,
    entries: list[dict[str, Any]],
    source_scope: str,
    reused_from_cache_id: str | None = None,
    parent_cache_id: str | None = None,
) -> dict[str, Any]:
    return {
        "cache_id": str(uuid.uuid4()),
        "created_at": _now_iso(),
        "topic": topic,
        "query": query,
        "reading_status": reading_status,
        "source_scope": source_scope,
        "entry_count": len(entries),
        "entries": entries,
        "reused_from_cache_id": reused_from_cache_id,
        "parent_cache_id": parent_cache_id,
    }


def _build_cache_note(
    *,
    topic: str,
    filtered_count: int,
    total_count: int,
    summary: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    top_clusters = (summary.get("clusters") or [])[:5]
    preview = (summary.get("priority_candidates") or [])[:5]
    cluster_text = "、".join(str(item.get("label") or "") for item in top_clusters[:3] if item.get("label")) or "暂无明显主题"
    return {
        "kind": "cached_subset_analysis",
        "topic": topic,
        "batch_index": 1,
        "batch_size": filtered_count,
        "processed_count": filtered_count,
        "total_count": total_count,
        "summary": f"{label}，当前命中 {filtered_count}/{total_count} 篇，主要主题：{cluster_text}。",
        "top_clusters": top_clusters,
        "priority_candidates": preview,
    }


async def _load_matching_entries(
    db: AsyncSession,
    *,
    owner_user_id: int,
    reading_status: str,
    query: str,
    max_entries: int,
) -> list[CandidateRecord]:
    stmt: Select[Any] = select(BibEntry).where(BibEntry.owner_user_id == owner_user_id)
    if reading_status.strip():
        stmt = stmt.where(BibEntry.reading_status == reading_status.strip())
    normalized_query = str(query or "").strip()
    if normalized_query and normalized_query != "*":
        like = f"%{normalized_query}%"
        stmt = stmt.where(
            or_(
                BibEntry.title.ilike(like),
                BibEntry.abstract.ilike(like),
                BibEntry.journal.ilike(like),
                BibEntry.keywords_json.ilike(like),
                BibEntry.user_tags_json.ilike(like),
            )
        )
    rows = (
        await db.execute(
            stmt.order_by(BibEntry.updated_at.desc(), BibEntry.created_at.desc()).limit(max_entries)
        )
    ).scalars().all()
    return [_entry_to_record(entry) for entry in rows]


async def analyze_reading_candidates(
    db: AsyncSession,
    *,
    owner_user_id: int,
    topic: str,
    reading_status: str = "none",
    query: str = "*",
    batch_size: int = BATCH_SIZE_DEFAULT,
    max_entries: int = 1200,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    journal_matcher = await build_prompt_journal_quality_matcher(db, user_id=owner_user_id)
    journal_scorer = make_journal_scorer(journal_matcher)
    records = await _load_matching_entries(
        db,
        owner_user_id=owner_user_id,
        reading_status=reading_status,
        query=query,
        max_entries=max(1, int(max_entries or 1200)),
    )
    total_count = len(records)
    batch_size = max(20, min(int(batch_size or BATCH_SIZE_DEFAULT), 200))
    cluster_counter: Counter[str] = Counter()
    tier_counter: Counter[str] = Counter()
    ranked_records: list[tuple[float, CandidateRecord, dict[str, Any]]] = []
    working_notes: list[dict[str, Any]] = []
    annotated_entries: list[dict[str, Any]] = []

    for batch_index, offset in enumerate(range(0, total_count, batch_size), start=1):
        batch_records = records[offset: offset + batch_size]
        batch_cluster_counter: Counter[str] = Counter()
        batch_tier_counter: Counter[str] = Counter()
        batch_ranked: list[tuple[float, CandidateRecord, dict[str, Any]]] = []

        for record in batch_records:
            cluster_label = _cluster_key(record)
            batch_cluster_counter[cluster_label] += 1
            score, detail = _priority_score(record, journal_scorer=journal_scorer)
            journal_quality = detail.get("journal_quality")
            if journal_quality:
                batch_tier_counter[str(journal_quality.get("label") or "高质量期刊")] += 1
                tier_counter[str(journal_quality.get("label") or "高质量期刊")] += 1
            batch_ranked.append((score, record, detail))
            ranked_records.append((score, record, detail))
            annotated_entries.append(
                _annotated_entry(
                    record,
                    cluster_label=cluster_label,
                    score=score,
                    detail=detail,
                )
            )

        _merge_counter(cluster_counter, batch_cluster_counter)
        note = _build_batch_note(
            topic=topic,
            batch_index=batch_index,
            batch_size=len(batch_records),
            processed_count=min(offset + len(batch_records), total_count),
            total_count=total_count,
            cluster_counter=batch_cluster_counter,
            journal_counter=batch_tier_counter,
            priority_records=batch_ranked,
        )
        working_notes.append(note)
        if progress_callback is not None:
            await progress_callback(
                {
                    "topic": topic,
                    "batch_index": batch_index,
                    "batch_size": len(batch_records),
                    "processed_count": note["processed_count"],
                    "total_count": total_count,
                    "working_note": note,
                    "top_clusters": note["top_clusters"],
                    "priority_preview": note["priority_candidates"],
                }
            )

    final_summary = _aggregate_final_summary(
        topic=topic,
        total_count=total_count,
        cluster_counter=cluster_counter,
        tier_counter=tier_counter,
        ranked_records=ranked_records,
    )
    analysis_cache = _build_analysis_cache(
        topic=topic,
        query=query,
        reading_status=reading_status,
        entries=sorted(
            annotated_entries,
            key=lambda item: float(item.get("priority_score") or 0.0),
            reverse=True,
        ),
        source_scope="full_library_analysis",
    )
    return {
        "topic": topic,
        "query": query,
        "reading_status": reading_status,
        "count": total_count,
        "batch_size": batch_size,
        "working_notes": working_notes,
        "analysis_summary": final_summary,
        "analysis_cache": analysis_cache,
        "note": "本结果优先依据本地期刊名录与题录元数据做候选排序，大模型可在此基础上补充解释。",
    }


def filter_analysis_cache(
    *,
    analysis_cache: dict[str, Any],
    topic: str,
    journal_tier_labels: list[str] | None = None,
    cluster_labels: list[str] | None = None,
    require_fulltext: bool | None = None,
    reading_status: str = "",
    max_entries: int = 0,
) -> dict[str, Any]:
    entries = [
        item for item in (analysis_cache.get("entries") or [])
        if isinstance(item, dict)
    ]
    journal_tier_labels = [str(item).strip() for item in (journal_tier_labels or []) if str(item).strip()]
    cluster_labels = [str(item).strip() for item in (cluster_labels or []) if str(item).strip()]
    total_count = len(entries)

    def _matches(item: dict[str, Any]) -> bool:
        if journal_tier_labels:
            label = str(((item.get("journal_quality") or {}).get("label")) or "").strip()
            if label not in journal_tier_labels:
                return False
        if cluster_labels:
            owned = {str(label).strip() for label in (item.get("cluster_labels") or []) if str(label).strip()}
            if not owned.intersection(cluster_labels):
                return False
        if require_fulltext is True and not bool(item.get("has_fulltext")):
            return False
        if require_fulltext is False and bool(item.get("has_fulltext")):
            return False
        if reading_status and str(item.get("reading_status") or "").strip() != reading_status.strip():
            return False
        return True

    filtered = [item for item in entries if _matches(item)]
    filtered.sort(key=lambda item: float(item.get("priority_score") or 0.0), reverse=True)
    if max_entries and max_entries > 0:
        filtered = filtered[:max_entries]

    summary = _aggregate_summary_from_dataset_entries(topic, filtered)
    filters_applied: list[str] = []
    if journal_tier_labels:
        filters_applied.append("期刊层级=" + " / ".join(journal_tier_labels))
    if cluster_labels:
        filters_applied.append("主题=" + " / ".join(cluster_labels))
    if require_fulltext is True:
        filters_applied.append("仅保留有全文")
    elif require_fulltext is False:
        filters_applied.append("仅保留无全文")
    if reading_status:
        filters_applied.append(f"reading_status={reading_status}")
    filter_label = "，".join(filters_applied) or "基于上一轮分析缓存继续筛选"
    note = _build_cache_note(
        topic=topic,
        filtered_count=len(filtered),
        total_count=total_count,
        summary=summary,
        label=filter_label,
    )
    next_cache = _build_analysis_cache(
        topic=topic,
        query=str(analysis_cache.get("query") or "*"),
        reading_status=reading_status or str(analysis_cache.get("reading_status") or ""),
        entries=filtered,
        source_scope="analysis_cache_subset",
        reused_from_cache_id=str(analysis_cache.get("cache_id") or ""),
        parent_cache_id=str(analysis_cache.get("cache_id") or ""),
    )
    return {
        "topic": topic,
        "count": len(filtered),
        "applied_filters": {
            "journal_tier_labels": journal_tier_labels,
            "cluster_labels": cluster_labels,
            "require_fulltext": require_fulltext,
            "reading_status": reading_status or "",
        },
        "working_notes": [note],
        "analysis_summary": summary,
        "analysis_cache": next_cache,
        "entries": filtered[:50],
        "note": "当前结果来自本会话上一轮分析缓存的子集筛选，未重新全量扫描文献库。",
    }
