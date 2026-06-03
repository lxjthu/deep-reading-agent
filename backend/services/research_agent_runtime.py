from __future__ import annotations

import hashlib
import json
import re
import uuid
from copy import deepcopy
from typing import Any

from backend.services.agent_errors import RuntimeNoticeCode
from backend.services.research_sufficiency import assess_evidence_sufficiency


CONTINUATION_PATTERNS = (
    "上一轮",
    "刚才",
    "这些文献",
    "这些论文",
    "这些",
    "那几篇",
    "那组",
    "上面提到",
    "前面",
    "刚刚",
    "继续",
    "continue",
    "continue again",
    "continue from",
    "continue with",
    "keep going",
    "based on the previous",
    "from the previous result set",
    "previous result set",
    "previous results",
    "prior result set",
    "these papers",
    "these entries",
    "those papers",
    "that result set",
    "above papers",
    "专注看",
    "只看",
    "聚焦",
    "其中",
    "这里面",
    "在这批里",
)

EXTERNAL_PATTERNS = (
    "cnki",
    "中国知网",
    "联网",
    "外部",
    "网页",
    "openalex",
    "unpaywall",
    "semantic scholar",
    "google scholar",
    "谷歌学术",
    "全文",
    "pdf",
)

EXECUTION_PATTERNS = (
    "启动",
    "开始",
    "执行",
    "导入",
    "批量精读",
    "精读",
    "分析这些文件",
    "start",
    "launch",
    "run",
    "execute",
    "import",
    "begin",
    "batch reading",
    "start reading",
    "read these papers",
    "analyze these files",
    "process these files",
)

STATUS_PATTERNS = (
    "任务状态",
    "进度",
    "job",
    "状态",
    "status",
    "progress",
    "running",
    "queued",
    "completed",
    "failed",
    "check progress",
    "check status",
    "job status",
)
COMPARE_PATTERNS = (
    "综述",
    "比较",
    "对比",
    "差异",
    "相同点",
    "异同",
    "总结",
    "summary",
    "summarize",
    "synthesis",
    "synthesize",
    "compare",
    "comparison",
    "differences",
    "similarities",
    "common themes",
    "common findings",
    "research gaps",
)

ANALYZE_PATTERNS = (
    "分类",
    "归类",
    "分组",
    "梳理",
    "优先精读",
    "优先阅读",
    "推荐先读",
    "表格",
    "未启动精读",
    "没有启动精读",
    "未精读",
    "classify",
    "cluster",
    "group",
    "prioritize",
    "priority reading",
    "recommend which papers",
    "make a table",
)

FORCE_FULL_ANALYSIS_PATTERNS = (
    "重新全量",
    "重新跑全量",
    "全量重跑",
    "从头分析",
    "重新分析全部",
    "忽略上次结果",
    "不要用之前结果",
    "重新扫描全部",
    "rerun full",
    "full rerun",
    "ignore previous result",
    "from scratch",
)

TOPIC_SHIFT_PATTERNS = (
    "换个话题",
    "换一个话题",
    "换个主题",
    "换一个主题",
    "换个方向",
    "换一个方向",
    "换个问题",
    "换一个问题",
    "换个研究问题",
    "换一个研究问题",
    "换个研究主题",
    "换一个研究主题",
    "另一个话题",
    "另外一个话题",
    "新的话题",
    "新话题",
    "新主题",
    "换成",
    "改看",
    "改成",
    "不看这些",
    "不看这批",
    "看别的",
    "看另一批",
    "look at another topic",
    "switch topic",
    "new topic",
    "different topic",
    "change topic",
)

ANALYSIS_SUBSET_PATTERNS = (
    "专注看",
    "只看",
    "聚焦",
    "其中",
    "筛出",
    "挑出",
    "限定",
    "top 5",
    "utd 24",
    "顶刊",
)

COUNT_PATTERNS = (
    "有多少",
    "多少篇",
    "多少条",
    "多少个",
    "总数",
    "一共多少",
    "共有多少",
    "几篇",
    "几条",
    "几篇论文",
    "count",
    "how many",
    "total number",
    "total count",
)

ENTRY_ID_TOOLS = {
    "research_search",
    "get_evidence_pack",
    "get_source_windows",
    "get_reading_context",
    "search_cnki",
    "lookup_english_fulltext",
}
EXTERNAL_TOOLS = {"search_cnki", "lookup_english_fulltext"}

JOURNAL_TIER_HINTS = {
    "Economics Top 5": ("economics top 5", "top 5", "aer", "qje", "jpe", "econometrica", "review of economic studies"),
    "Management UTD 24 (Selected)": ("management utd 24", "utd 24", "amj", "amr", "asq", "smj", "orgsci", "misq", "isr"),
    "Finance Top 3": ("finance top 3", "journal of finance", "jfe", "rfs"),
    "Chinese Top Tier": ("chinese top tier", "中文顶刊", "国内顶刊", "管理世界", "经济研究"),
    "General Science": ("general science", "nature", "science", "pnas"),
}


def _compact_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _lower_text(value: str) -> str:
    return _compact_text(value).lower()


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = _lower_text(text)
    return any(pattern.lower() in lowered for pattern in patterns)


def _make_digest(name: str, args: dict[str, Any]) -> str:
    payload = json.dumps({"name": name, "args": args}, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _is_empty_result(result: dict[str, Any]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("error"):
        return True
    if isinstance(result.get("count"), int) and result["count"] == 0:
        return True
    for key in ("entries", "items", "papers", "results", "open_urls"):
        value = result.get(key)
        if isinstance(value, list):
            return len(value) == 0
    return False


def _short_text(value: Any, limit: int = 80) -> str:
    text = _compact_text(str(value or ""))
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _working_note_summary(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": note.get("kind"),
        "topic": note.get("topic"),
        "batch_index": note.get("batch_index"),
        "processed_count": note.get("processed_count"),
        "total_count": note.get("total_count"),
        "summary": note.get("summary"),
        "top_clusters": (note.get("top_clusters") or [])[:5],
        "priority_candidates": (note.get("priority_candidates") or [])[:5],
    }


def _analysis_cache(state: dict[str, Any] | None) -> dict[str, Any]:
    cache = ((state or {}).get("analysis_cache") or {})
    return cache if isinstance(cache, dict) else {}


def _analysis_cache_refs(state: dict[str, Any] | None) -> list[dict[str, str]]:
    return _result_entries((_analysis_cache(state).get("entries") or []))


def _infer_journal_tier_labels(raw_message: str) -> list[str]:
    lowered = _lower_text(raw_message)
    matched: list[str] = []
    for label, hints in JOURNAL_TIER_HINTS.items():
        if any(hint.lower() in lowered for hint in hints):
            matched.append(label)
    return matched


def _infer_cluster_labels(raw_message: str, state: dict[str, Any] | None) -> list[str]:
    lowered = _lower_text(raw_message)
    summary = ((_analysis_cache(state).get("analysis_summary") or {}))
    labels = [str(item.get("label") or "") for item in (summary.get("clusters") or []) if str(item.get("label") or "").strip()]
    matched: list[str] = []
    for label in labels:
        candidates = {_lower_text(label)}
        candidates.update(
            _lower_text(part)
            for part in re.split(r"[／/]", label)
            if _lower_text(part)
        )
        if any(candidate and candidate in lowered for candidate in candidates):
            matched.append(label)
    return matched


def _is_explicit_topic_shift(raw_message: str) -> bool:
    return _contains_any(raw_message, TOPIC_SHIFT_PATTERNS)


def _summarize_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ("query", "question", "topic", "mode", "job_id", "entry_id", "file_id", "batch_id"):
        value = args.get(key)
        if value not in (None, "", [], {}):
            summary[key] = _short_text(value)
    for key in ("entry_ids", "file_ids", "titles", "keywords", "analysis_dims"):
        value = args.get(key)
        if isinstance(value, list) and value:
            items = [_short_text(item, limit=40) for item in value[:3] if item not in (None, "")]
            if items:
                summary[key] = items
                summary[f"{key}_count"] = len(value)
    for key in ("limit", "limit_entries", "limit_evidence_per_entry", "max_files", "max_entries", "max_items"):
        value = args.get(key)
        if value not in (None, "", []):
            summary[key] = value
    for key in ("recursive", "include_source_text", "include_user_notes", "include_ai_notes"):
        value = args.get(key)
        if isinstance(value, bool):
            summary[key] = value
    return summary


def _summarize_tool_result(
    *,
    name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    empty: bool,
    blocked_by_policy: bool,
) -> dict[str, Any]:
    status = "success"
    result_summary = ""
    code = str(result.get("code") or "")
    message = str(result.get("message") or result.get("error") or "")

    if blocked_by_policy:
        status = "blocked"
        result_summary = "已被运行时策略拦截"
    elif result.get("proposal_id"):
        status = "proposal"
        action_type = str(result.get("action_type") or name)
        result_summary = f"已生成执行提案：{action_type}"
    elif result.get("error"):
        status = "error"
        result_summary = _short_text(message or "工具执行失败")
    elif empty:
        status = "empty"
        result_summary = "未返回有效结果"
    elif name == "count_library" and isinstance(result.get("count"), int):
        result_summary = f"共 {int(result['count'])} 篇文献"
    elif isinstance(result.get("total_count"), int) and isinstance(result.get("returned_count"), int):
        result_summary = (
            f"命中总数 {int(result.get('total_count') or 0)} 篇，"
            f"当前返回 {int(result.get('returned_count') or 0)} 篇"
        )
    elif isinstance(result.get("count"), int):
        result_summary = f"返回 {int(result['count'])} 条结果"
    elif isinstance(result.get("candidate_count"), int) or isinstance(result.get("relevant_count"), int):
        result_summary = (
            f"候选 {int(result.get('candidate_count') or 0)} 条，"
            f"相关 {int(result.get('relevant_count') or 0)} 条"
        )
    elif isinstance(result.get("selected_count"), int):
        result_summary = f"选中 {int(result.get('selected_count') or 0)} 个对象"
    elif isinstance(result.get("tasks"), list):
        result_summary = f"返回 {len(result.get('tasks') or [])} 个任务"
    elif isinstance(result.get("entries"), list):
        result_summary = f"返回 {len(result.get('entries') or [])} 篇文献"
    elif isinstance(result.get("papers"), list):
        result_summary = f"扫描得到 {len(result.get('papers') or [])} 条候选"
    elif isinstance(result.get("open_urls"), list):
        result_summary = f"生成 {len(result.get('open_urls') or [])} 个外部链接"
    else:
        result_summary = "已完成工具调用"

    return {
        "tool": name,
        "status": status,
        "blocked": blocked_by_policy,
        "empty": empty,
        "hit": bool(not blocked_by_policy and not empty and not result.get("error")),
        "arguments_summary": _summarize_tool_args(args),
        "result_summary": result_summary,
        "code": code or None,
        "message": _short_text(message, limit=120) if message else None,
    }


def _entry_ref(item: dict[str, Any]) -> dict[str, str]:
    entry_id = str(item.get("entry_id") or item.get("id") or "").strip()
    title = str(item.get("title") or "").strip()
    return {"entry_id": entry_id, "title": title}


def _result_entries(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        ref = _entry_ref(item)
        if not ref["entry_id"] or ref["entry_id"] in seen:
            continue
        seen.add(ref["entry_id"])
        refs.append(ref)
    return refs


def _entry_ids_from_context(resolved_context: dict[str, Any]) -> list[str]:
    refs = resolved_context.get("entries") or []
    return [str(item.get("entry_id")) for item in refs if item.get("entry_id")]


def _resolved_entry_count(resolved_context: dict[str, Any]) -> int:
    return len(_entry_ids_from_context(resolved_context))


def _result_set_tool_recommendations() -> list[str]:
    return ["get_evidence_pack", "research_search", "get_reading_context", "get_source_windows"]


def _extract_last_execution_jobs(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    last_execution = (state or {}).get("last_execution") or {}
    tasks = last_execution.get("tasks") or []
    refs: list[dict[str, Any]] = []
    if isinstance(last_execution.get("job_id"), str) and last_execution.get("job_id"):
        refs.append(
            {
                "job_id": str(last_execution["job_id"]),
                "status": str(last_execution.get("status") or ""),
                "file_name": str(last_execution.get("file_name") or ""),
            }
        )
    for task in tasks:
        if not isinstance(task, dict):
            continue
        job_id = str(task.get("job_id") or "")
        if not job_id:
            continue
        refs.append(
            {
                "job_id": job_id,
                "status": str(task.get("status") or ""),
                "file_name": str(task.get("file_name") or ""),
            }
        )
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in refs:
        job_id = item["job_id"]
        if job_id in seen:
            continue
        seen.add(job_id)
        deduped.append(item)
    return deduped


def _preferred_job_id(state: dict[str, Any] | None) -> str:
    jobs = _extract_last_execution_jobs(state)
    for preferred_status in ("running", "queued", "pending", "success", "completed", "failed"):
        for item in jobs:
            if item.get("status") == preferred_status:
                return str(item["job_id"])
    return str(jobs[0]["job_id"]) if jobs else ""


def apply_execution_result_to_state(
    state: dict[str, Any] | None,
    *,
    proposal_id: str,
    action_type: str,
    proposal_status: str,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    next_state = deepcopy(state or {})
    pending = next_state.get("pending_proposal") or {}
    if pending.get("proposal_id") == proposal_id:
        next_state["pending_proposal"] = None

    result = result or {}
    batch = result.get("batch") or {}
    batch_id = result.get("batch_id")
    raw_tasks = result.get("tasks") or []
    if isinstance(batch, dict):
        batch_id = batch_id or batch.get("batch_id")
        if not raw_tasks:
            raw_tasks = batch.get("tasks") or []
    tasks: list[dict[str, Any]] = []
    for task in raw_tasks:
        if not isinstance(task, dict):
            continue
        job_id = str(task.get("job_id") or task.get("task_id") or "")
        if not job_id:
            continue
        tasks.append(
            {
                "job_id": job_id,
                "file_id": task.get("file_id"),
                "file_name": task.get("file_name"),
                "status": task.get("status"),
            }
        )

    next_state["last_execution"] = {
        "proposal_id": proposal_id,
        "action_type": action_type,
        "status": proposal_status,
        "job_id": result.get("job_id"),
        "batch_id": batch_id,
        "mode": result.get("mode"),
        "selected_count": result.get("selected_count"),
        "source": result.get("source"),
        "tasks": tasks[:8],
        "error": result.get("error"),
    }
    return next_state


def build_runtime_notice(
    *,
    code: str,
    message: str,
    severity: str = "warning",
    tool: str | None = None,
    blocked_tool: str | None = None,
    suggested_tools: list[str] | None = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "severity": severity,
        "tool": tool,
        "blocked_tool": blocked_tool or tool,
        "suggested_tools": suggested_tools or [],
        "recommendations": recommendations or [],
    }


def build_task_frame(message: str, state: dict[str, Any] | None) -> dict[str, Any]:
    raw = _compact_text(message)
    continuation = _contains_any(raw, CONTINUATION_PATTERNS)
    wants_external = _contains_any(raw, EXTERNAL_PATTERNS)
    wants_execution = _contains_any(raw, EXECUTION_PATTERNS)
    wants_status = _contains_any(raw, STATUS_PATTERNS)
    wants_compare = _contains_any(raw, COMPARE_PATTERNS)
    wants_analyze = _contains_any(raw, ANALYZE_PATTERNS)
    wants_count = _contains_any(raw, COUNT_PATTERNS)
    force_full_analysis = _contains_any(raw, FORCE_FULL_ANALYSIS_PATTERNS)
    explicit_topic_shift = _is_explicit_topic_shift(raw)
    has_result_set = bool((state or {}).get("last_result_set"))
    has_analysis_cache = bool(_analysis_cache_refs(state))
    wants_subset = _contains_any(raw, ANALYSIS_SUBSET_PATTERNS)
    default_cache_followup = (
        has_analysis_cache
        and not force_full_analysis
        and not explicit_topic_shift
        and not wants_status
        and not wants_count
        and not wants_execution
        and not wants_external
    )

    if wants_status:
        intent = "check_status"
    elif default_cache_followup:
        intent = "analyze_cached_collection"
    elif wants_analyze:
        intent = "analyze_collection"
    elif wants_count:
        intent = "library_count"
    elif wants_execution:
        intent = "start_job"
    elif wants_external:
        intent = "external_lookup"
    elif wants_compare:
        intent = "summarize_topic"
    elif continuation and has_result_set:
        intent = "continue_result_set"
    else:
        intent = "library_lookup"

    return {
        "turn_id": str(uuid.uuid4()),
        "raw_message": raw,
        "intent": intent,
        "continuation_ref": continuation or default_cache_followup,
        "requires_local_search": intent in {"library_lookup", "library_count", "summarize_topic", "continue_result_set", "analyze_collection", "analyze_cached_collection"},
        "requires_external_search": wants_external,
        "requires_write_proposal": intent == "start_job",
        "user_requested_external": wants_external,
        "prefers_result_set_tools": continuation and intent in {"summarize_topic", "continue_result_set"},
        "force_full_analysis": force_full_analysis,
        "explicit_topic_shift": explicit_topic_shift,
        "has_analysis_cache": has_analysis_cache,
        "prefer_analysis_cache": default_cache_followup and intent == "analyze_cached_collection",
        "ambiguities": [],
    }


def resolve_context_refs(task_frame: dict[str, Any], state: dict[str, Any] | None) -> dict[str, Any]:
    state = state or {}
    if not task_frame.get("continuation_ref") and not task_frame.get("prefer_analysis_cache"):
        return {"status": "not_needed", "source": None, "entries": []}

    for source in ("analysis_cache", "selected_entries", "last_result_set", "last_evidence_pack"):
        candidate = state.get(source)
        if not candidate:
            continue
        if source == "analysis_cache":
            entries = candidate.get("entries") or []
        elif source == "selected_entries":
            entries = candidate
        elif source == "last_result_set":
            entries = candidate.get("entries") or []
        else:
            entries = candidate.get("entries") or []
        refs = _result_entries(entries)
        if refs:
            return {
                "status": "resolved",
                "source": source,
                "entries": refs,
                "count": len(refs),
                "result_set_id": candidate.get("result_set_id") if isinstance(candidate, dict) else None,
                "cache_id": candidate.get("cache_id") if isinstance(candidate, dict) else None,
            }

    return {
        "status": "needs_clarification",
        "source": None,
        "entries": [],
        "reason": "continuation_without_context",
    }


def build_runtime_system_prompts(
    task_frame: dict[str, Any],
    resolved_context: dict[str, Any],
    state: dict[str, Any] | None,
) -> list[str]:
    prompts: list[str] = []
    if resolved_context.get("status") == "resolved":
        refs = resolved_context.get("entries") or []
        preview = refs[:8]
        prompts.append(
            "当前用户正在承接上一轮结果集。若本轮需要 entry_ids，请优先使用这些对象，不要自行编造新的 id："
            + json.dumps(
                {
                    "source": resolved_context.get("source"),
                    "count": len(refs),
                    "entries": preview,
                },
                ensure_ascii=False,
            )
        )
        if task_frame.get("prefers_result_set_tools") and len(refs) > 1:
            prompts.append(
                "本轮目标是基于上一轮多篇文献做继续分析/总结。优先使用 get_evidence_pack、research_search、"
                "get_reading_context 这类结果集级工具；除非用户明确要求单篇详情，否则不要对每篇文献逐个调用 get_entry_detail。"
            )
    elif resolved_context.get("status") == "needs_clarification":
        prompts.append("用户看起来在引用上一轮对象，但当前会话没有可解析的结果集。不要编造 entry_id；必要时先要求澄清。")

    last_result_set = (state or {}).get("last_result_set") or {}
    if last_result_set:
        prompts.append(
            "最近一次稳定结果集摘要："
            + json.dumps(
                {
                    "count": last_result_set.get("count"),
                    "query_summary": last_result_set.get("query_summary"),
                    "entries": (last_result_set.get("entries") or [])[:6],
                },
                ensure_ascii=False,
            )
        )
    analysis_cache = _analysis_cache(state)
    if analysis_cache:
        prompts.append(
            "当前会话已有持久化分析缓存："
            + json.dumps(
                {
                    "cache_id": analysis_cache.get("cache_id"),
                    "source_scope": analysis_cache.get("source_scope"),
                    "entry_count": analysis_cache.get("entry_count"),
                    "topic": analysis_cache.get("topic"),
                    "clusters": ((analysis_cache.get("analysis_summary") or {}).get("clusters") or [])[:6],
                    "journal_tier_distribution": ((analysis_cache.get("analysis_summary") or {}).get("journal_tier_distribution") or [])[:6],
                },
                ensure_ascii=False,
            )
        )

    if task_frame.get("intent") == "library_count":
        prompts.append(
            "本轮用户优先是在问文献总数/数量。优先调用 count_library 直接读取数据库总数，"
            "不要先列标题，也不要把前 20 条误当成总量。只有在用户明确要求列出明细时，"
            "才继续调用 search_library 分页查看，并说明当前页与总数。"
        )
    if task_frame.get("intent") == "analyze_collection":
        prompts.append(
            "本轮是大集合分类/优先级分析场景。优先调用 analyze_reading_candidates，"
            "不要先枚举所有标题。该工具会分批处理文献、沉淀工作笔记，并返回候选表格。"
        )
        prompts.append(
            "回答时先引用本地工作笔记和期刊名录命中结果，再补充模型解释；"
            "不要把模型世界知识说成数据库已有事实。"
        )
        prompts.append(
            "做主题分类时，优先合并大小写变体、缩写和同义词（如 GenAI/Generative AI、Climate Change/climate change）；"
            "除非确实无法归类，不要把大量文献笼统归入“其他”。"
        )
    if task_frame.get("intent") == "analyze_cached_collection":
        prompts.append(
            "本轮默认复用当前会话已有的 analysis_cache，不要重新全量扫描文献库。"
            "优先调用 filter_analysis_cache 在上一轮已标注的论文集合上继续筛选、细化和生成表格。"
        )
        if task_frame.get("force_full_analysis"):
            prompts.append("用户已明确要求重新全量分析，本轮允许放弃缓存重新跑全量。")

    last_execution_jobs = _extract_last_execution_jobs(state)
    last_execution = (state or {}).get("last_execution") or {}
    if task_frame.get("intent") == "check_status" and last_execution_jobs:
        prompts.append(
            "当前会话最近一次已确认执行的任务摘要："
            + json.dumps(
                {
                    "proposal_id": last_execution.get("proposal_id"),
                    "action_type": last_execution.get("action_type"),
                    "batch_id": last_execution.get("batch_id"),
                    "jobs": last_execution_jobs[:6],
                },
                ensure_ascii=False,
            )
        )
        prompts.append("查询进度时优先使用真实 job_id，不要把 proposal_id 当成 job_id。")

    if not task_frame.get("user_requested_external"):
        prompts.append("本轮用户没有明确授权外部检索；除非用户明确要求 CNKI/全文/PDF/联网/网页检索，否则不要调用 external_read 工具。")
    return prompts


def normalize_tool_args(
    name: str,
    args: dict[str, Any],
    *,
    task_frame: dict[str, Any],
    resolved_context: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = deepcopy(args)

    if name == "search_library":
        query = _compact_text(str(normalized.get("query") or ""))
        normalized["query"] = "" if query == "*" else query
        return normalized

    if name == "analyze_reading_candidates":
        if not str(normalized.get("topic") or "").strip():
            normalized["topic"] = task_frame.get("raw_message") or ""
        if not str(normalized.get("query") or "").strip():
            normalized["query"] = "*"
        raw_message = task_frame.get("raw_message") or ""
        if ("未启动精读" in raw_message) or ("没有启动精读" in raw_message) or ("未精读" in raw_message):
            normalized["reading_status"] = "none"
        normalized["batch_size"] = max(20, min(int(normalized.get("batch_size") or 100), 200))
        normalized["max_entries"] = max(1, min(int(normalized.get("max_entries") or 1200), 2000))
        return normalized

    if name == "filter_analysis_cache":
        if not str(normalized.get("topic") or "").strip():
            normalized["topic"] = task_frame.get("raw_message") or ""
        normalized["journal_tier_labels"] = [
            str(item).strip()
            for item in (normalized.get("journal_tier_labels") or _infer_journal_tier_labels(task_frame.get("raw_message") or ""))
            if str(item).strip()
        ]
        normalized["cluster_labels"] = [
            str(item).strip()
            for item in (normalized.get("cluster_labels") or _infer_cluster_labels(task_frame.get("raw_message") or "", state))
            if str(item).strip()
        ]
        if normalized.get("require_fulltext") not in (True, False):
            if _contains_any(task_frame.get("raw_message") or "", ("有全文", "全文可用", "with full text", "full text")):
                normalized["require_fulltext"] = True
        if not str(normalized.get("reading_status") or "").strip():
            raw_message = task_frame.get("raw_message") or ""
            if ("未启动精读" in raw_message) or ("没有启动精读" in raw_message) or ("未精读" in raw_message):
                normalized["reading_status"] = "none"
        raw_max_entries = normalized.get("max_entries")
        if raw_max_entries in (None, "", []):
            normalized["max_entries"] = 0
        else:
            normalized["max_entries"] = max(0, min(int(raw_max_entries), 2000))
        return normalized

    if name in {"scan_input_folder", "import_folder_and_start_reading"}:
        if not str(normalized.get("topic") or "").strip():
            normalized["topic"] = "*"
        normalized["max_files"] = max(1, min(int(normalized.get("max_files") or 100), 500))
        normalized["offset"] = max(0, int(normalized.get("offset") or 0))
        return normalized

    if name in ENTRY_ID_TOOLS:
        resolved_ids = _entry_ids_from_context(resolved_context)
        explicit_ids = [str(item) for item in (normalized.get("entry_ids") or []) if item]
        if resolved_ids and task_frame.get("continuation_ref"):
            if not explicit_ids:
                normalized["entry_ids"] = resolved_ids
            elif all(re.fullmatch(r"\d{5,}", item or "") for item in explicit_ids):
                normalized["entry_ids"] = resolved_ids

    if name in {"research_search", "get_evidence_pack"} and not normalized.get("question"):
        normalized["question"] = task_frame.get("raw_message") or ""

    if name == "get_job_status":
        explicit_job_id = str(normalized.get("job_id") or "").strip()
        pending_proposal_id = str(((state or {}).get("pending_proposal") or {}).get("proposal_id") or "")
        last_execution = (state or {}).get("last_execution") or {}
        last_execution_proposal_id = str(last_execution.get("proposal_id") or "")
        preferred_job_id = _preferred_job_id(state)
        if not explicit_job_id and preferred_job_id:
            normalized["job_id"] = preferred_job_id
        elif explicit_job_id and preferred_job_id and explicit_job_id in {pending_proposal_id, last_execution_proposal_id}:
            normalized["job_id"] = preferred_job_id

    return normalized


def enforce_tool_policy(
    name: str,
    args: dict[str, Any],
    *,
    task_frame: dict[str, Any],
    state: dict[str, Any],
    resolved_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    resolved_context = resolved_context or {}
    recommendations = [
        "优先复用上一轮结果集中的文献对象。",
        "如需继续总结多篇文献，优先使用结果集级工具而不是逐篇详情。",
    ]

    if (
        task_frame.get("continuation_ref")
        and resolved_context.get("status") == "needs_clarification"
        and name in ENTRY_ID_TOOLS.union({"get_entry_detail"})
    ):
        return {
            "error": RuntimeNoticeCode.CONSENT_REQUIRED.value,
            "code": RuntimeNoticeCode.CONTINUATION_CONTEXT_REQUIRED.value,
            "message": "你在承接上一轮对象，但当前会话没有可解析的结果集。请先澄清要继续分析哪组文献，或先重新检索并形成结果集。",
            "tool": name,
            "arguments": args,
            "recommendations": [
                "先让用户明确“上一轮”指的是哪组文献。",
                "或先调用 search_library / research_search 重新形成结果集后再继续。",
            ],
        }

    if name in EXTERNAL_TOOLS and not task_frame.get("user_requested_external"):
        return {
            "error": RuntimeNoticeCode.CONSENT_REQUIRED.value,
            "code": RuntimeNoticeCode.EXTERNAL_CONSENT_REQUIRED.value,
            "message": "本轮用户未明确要求联网检索；请先询问是否允许进行外部检索。",
            "tool": name,
            "recommendations": ["先确认用户是否允许联网检索或查找全文。"],
        }

    if (
        name == "get_entry_detail"
        and task_frame.get("prefers_result_set_tools")
        and _resolved_entry_count(resolved_context) > 1
    ):
        return {
            "error": RuntimeNoticeCode.INEFFICIENT_TOOL_PATH.value,
            "code": RuntimeNoticeCode.PREFER_RESULT_SET_TOOLS.value,
            "message": "当前是承接上一轮多篇文献的继续分析场景。请优先使用 get_evidence_pack、research_search 或 get_reading_context 处理整组文献，除非用户明确要求查看单篇详情。",
            "tool": name,
            "arguments": args,
            "suggested_tools": _result_set_tool_recommendations(),
            "recommendations": recommendations,
        }

    if (
        name == "search_library"
        and task_frame.get("prefers_result_set_tools")
        and _resolved_entry_count(resolved_context) > 1
    ):
        return {
            "error": RuntimeNoticeCode.INEFFICIENT_TOOL_PATH.value,
            "code": RuntimeNoticeCode.PREFER_CONTEXTUAL_RESULT_SET.value,
            "message": "当前已经有上一轮结果集，继续分析时不应回退到重新搜全库。请直接在这组文献上调用 get_evidence_pack、research_search、get_reading_context 或 get_source_windows。",
            "tool": name,
            "arguments": args,
            "suggested_tools": _result_set_tool_recommendations(),
            "recommendations": recommendations,
        }

    if name == "filter_analysis_cache" and not _analysis_cache_refs(state):
        return {
            "error": RuntimeNoticeCode.CONTEXT_REQUIRED.value,
            "code": RuntimeNoticeCode.ANALYSIS_CACHE_REQUIRED.value,
            "message": "当前会话还没有可复用的 analysis_cache。请先执行一次 analyze_reading_candidates 形成论文级标注缓存，再继续做子集筛选。",
            "tool": name,
            "arguments": args,
            "suggested_tools": ["analyze_reading_candidates"],
            "recommendations": [
                "先对目标文献集合做一次批量分析，形成持久化 analysis_cache。",
                "如果用户明确要求从头分析，可直接调用 analyze_reading_candidates。",
            ],
        }

    if task_frame.get("intent") == "analyze_cached_collection" and name != "filter_analysis_cache":
        return {
            "error": RuntimeNoticeCode.INEFFICIENT_TOOL_PATH.value,
            "code": RuntimeNoticeCode.PREFER_ANALYSIS_CACHE_FILTER.value,
            "message": "当前会话已有持久化分析缓存，且用户未要求重新全量分析。请优先使用 filter_analysis_cache 在上一轮已标注的论文集合上继续筛选，而不是重新扫全库。",
            "tool": name,
            "arguments": args,
            "suggested_tools": ["filter_analysis_cache"],
            "recommendations": [
                "先复用 analysis_cache 过滤顶刊、主题或是否有全文。",
                "只有用户明确要求重新全量分析时，才重新调用 analyze_reading_candidates。",
            ],
        }

    if task_frame.get("intent") == "analyze_collection" and name in {"search_library", "research_search", "get_evidence_pack"}:
        return {
            "error": RuntimeNoticeCode.INEFFICIENT_TOOL_PATH.value,
            "code": RuntimeNoticeCode.PREFER_BATCH_ANALYSIS_TOOL.value,
            "message": "当前是大集合分类/优先级分析场景。请优先使用 analyze_reading_candidates 做分批分析、结构化工作笔记和候选排序，不要先走全量枚举检索。",
            "tool": name,
            "arguments": args,
            "suggested_tools": ["analyze_reading_candidates"],
            "recommendations": [
                "先用 analyze_reading_candidates 对大集合做分批分析。",
                "如需补证据，再对候选子集调用 get_evidence_pack 或 research_search。",
            ],
        }

    runtime = state.setdefault("_runtime", {})
    recent_calls = runtime.get("recent_calls") or []
    key = _make_digest(name, args)
    repeated_empty = [item for item in recent_calls[-2:] if item.get("key") == key and item.get("empty")]
    if len(repeated_empty) >= 2:
        return {
            "error": RuntimeNoticeCode.BUDGET_EXHAUSTED.value,
            "code": RuntimeNoticeCode.DUPLICATE_TOOL_CALL_BLOCKED.value,
            "message": "相同工具和参数已经连续空结果，已阻止继续空转。请改用上一轮结果集、缩小范围，或先澄清目标对象。",
            "tool": name,
            "arguments": args,
            "recommendations": [
                "不要重复提交相同工具和参数。",
                "优先改用上一轮结果集，或缩小查询范围后再继续。",
            ],
        }

    if name == "search_library":
        empty_count = int((runtime.get("empty_tool_counts") or {}).get("search_library") or 0)
        total_count = int((runtime.get("tool_counts") or {}).get("search_library") or 0)
        if empty_count >= 3 or total_count >= 5:
            return {
                "error": RuntimeNoticeCode.BUDGET_EXHAUSTED.value,
                "code": RuntimeNoticeCode.SEARCH_LIBRARY_BUDGET_EXHAUSTED.value,
                "message": "search_library 已多次未有效收敛。请优先复用上一轮结果集、改用 research_search，或要求用户缩小范围。",
                "tool": name,
                "recommended_query_mode": "research_search",
                "recommendations": [
                    "优先切换到 research_search。",
                    "如果仍需搜索，请要求用户缩小主题或限定文献范围。",
                ],
            }

    return None


def build_stop_summary(
    *,
    task_frame: dict[str, Any],
    state: dict[str, Any] | None,
    reason: str,
    max_tool_rounds: int | None = None,
) -> dict[str, Any]:
    state = state or {}
    count = int(((state.get("last_result_set") or {}).get("count") or 0))
    recommendations = [
        "优先复用上一轮结果集继续提问。",
        "把问题缩小到更具体的主题、文献组或对象。",
    ]
    if reason == "max_tool_rounds_reached":
        message = "本轮工具调用已达到上限。建议直接基于当前结果集继续提问，或缩小范围后再继续。"
        if count > 0:
            message = f"本轮工具调用已达到上限；当前已有 {count} 篇文献结果可继续复用。"
        if max_tool_rounds:
            recommendations.append(f"本轮已使用 {max_tool_rounds} 轮工具调用，请避免重复无效搜索。")
    else:
        message = "本轮已停止，请基于当前结果集或更明确的目标继续。"

    return {
        "code": reason,
        "severity": "warning",
        "message": message,
        "intent": task_frame.get("intent"),
        "result_set_count": count,
        "budget_snapshot": state.get("budget_snapshot") or {},
        "recommendations": recommendations,
    }


def append_working_note(
    state: dict[str, Any],
    note: dict[str, Any],
    *,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    next_state = deepcopy(state)
    notes = list(next_state.get("working_notes") or [])
    notes.append(note)
    next_state["working_notes"] = notes[-20:]
    next_state["last_working_note"] = note
    if summary:
        next_state["last_analysis_summary"] = summary
    return next_state


def update_state_after_tool(
    state: dict[str, Any],
    *,
    name: str,
    args: dict[str, Any],
    result: dict[str, Any],
    blocked_by_policy: bool = False,
) -> dict[str, Any]:
    next_state = deepcopy(state)
    runtime = next_state.setdefault("_runtime", {})
    tool_counts = runtime.setdefault("tool_counts", {})
    empty_tool_counts = runtime.setdefault("empty_tool_counts", {})
    recent_calls = runtime.setdefault("recent_calls", [])

    empty = _is_empty_result(result)
    tool_counts[name] = int(tool_counts.get(name) or 0) + 1
    if empty:
        empty_tool_counts[name] = int(empty_tool_counts.get(name) or 0) + 1
    recent_calls.append(
        {
            "name": name,
            "key": _make_digest(name, args),
            "empty": empty,
        }
    )
    runtime["recent_calls"] = recent_calls[-12:]
    next_state["budget_snapshot"] = {
        "tool_counts": tool_counts,
        "empty_tool_counts": empty_tool_counts,
    }
    next_state["last_tool"] = {
        "name": name,
        "arguments": args,
        "empty": empty,
    }
    recent_tool_trace = list(next_state.get("recent_tool_trace") or [])
    recent_tool_trace.append(
        _summarize_tool_result(
            name=name,
            args=args,
            result=result,
            empty=empty,
            blocked_by_policy=blocked_by_policy,
        )
    )
    next_state["recent_tool_trace"] = recent_tool_trace[-12:]
    next_state["last_stop_summary"] = None

    if isinstance(result, dict) and result.get("code") and result.get("message"):
        next_state["last_runtime_notice"] = build_runtime_notice(
            code=str(result.get("code") or "runtime_notice"),
            message=str(result.get("message") or ""),
            severity="warning" if result.get("error") else "info",
            tool=name,
            blocked_tool=str(result.get("tool") or name),
            suggested_tools=[str(item) for item in (result.get("suggested_tools") or []) if item],
            recommendations=[str(item) for item in (result.get("recommendations") or []) if item],
        )
    elif not result.get("error"):
        next_state["last_runtime_notice"] = None

    if name in {"search_library", "research_search", "get_evidence_pack", "get_reading_context"}:
        raw_entries = result.get("entries") or []
        refs = _result_entries(raw_entries if isinstance(raw_entries, list) else [])
        if refs:
            next_state["last_result_set"] = {
                "result_set_id": str(uuid.uuid4()),
                "source_tool": name,
                "query_summary": str(
                    args.get("question")
                    or args.get("query")
                    or args.get("topic")
                    or next_state.get("active_task_frame", {}).get("raw_message")
                    or ""
                ),
                "count": len(refs),
                "entries": refs,
            }
            next_state["selected_entries"] = refs[:20]

    if name == "get_evidence_pack" and isinstance(result.get("entries"), list):
        refs = _result_entries(result["entries"])
        tier_counts: dict[str, int] = {}
        for entry in result["entries"]:
            if not isinstance(entry, dict):
                continue
            for evidence in entry.get("evidence") or []:
                if not isinstance(evidence, dict):
                    continue
                tier = str(evidence.get("source_tier") or "")
                if tier:
                    tier_counts[tier] = tier_counts.get(tier, 0) + 1
        next_state["last_evidence_pack"] = {
            "evidence_pack_id": str(uuid.uuid4()),
            "question": str(result.get("question") or args.get("question") or ""),
            "count": len(refs),
            "entries": refs,
            "tier_summary": tier_counts,
        }
        next_state["last_sufficiency"] = assess_evidence_sufficiency(
            result,
            user_requested_external=bool(
                (next_state.get("active_task_frame") or {}).get("user_requested_external")
            ),
        )

    if name in {"analyze_reading_candidates", "filter_analysis_cache"}:
        working_notes = result.get("working_notes") or []
        if isinstance(working_notes, list) and working_notes:
            next_state["working_notes"] = working_notes[-20:]
            next_state["last_working_note"] = working_notes[-1]
        if isinstance(result.get("analysis_summary"), dict):
            next_state["last_analysis_summary"] = result["analysis_summary"]
        if isinstance(result.get("analysis_cache"), dict):
            next_state["analysis_cache"] = result["analysis_cache"]
            next_state["analysis_cache"]["analysis_summary"] = result.get("analysis_summary") or {}
            refs = _result_entries((result.get("analysis_cache") or {}).get("entries") or [])
            if refs:
                next_state["last_result_set"] = {
                    "result_set_id": str(uuid.uuid4()),
                    "source_tool": name,
                    "query_summary": str(
                        args.get("topic")
                        or next_state.get("active_task_frame", {}).get("raw_message")
                        or ""
                    ),
                    "count": len(refs),
                    "entries": refs,
                }
                next_state["selected_entries"] = refs[:20]

    if isinstance(result, dict) and result.get("proposal_id"):
        next_state["pending_proposal"] = {
            "proposal_id": result.get("proposal_id"),
            "action_type": result.get("action_type"),
            "status": result.get("status"),
        }

    return next_state


def summarize_state_for_ui(state: dict[str, Any] | None) -> dict[str, Any]:
    state = state or {}
    last_result_set = state.get("last_result_set") or {}
    last_evidence_pack = state.get("last_evidence_pack") or {}
    last_runtime_notice = state.get("last_runtime_notice") or {}
    last_stop_summary = state.get("last_stop_summary") or {}
    last_agent_error = state.get("last_agent_error") or {}
    last_sufficiency = state.get("last_sufficiency") or {}
    last_scan = state.get("last_scan") or {}
    working_notes = state.get("working_notes") or []
    last_analysis_summary = state.get("last_analysis_summary") or {}
    analysis_cache = _analysis_cache(state)
    return {
        "active_task_frame": state.get("active_task_frame") or {},
        "last_result_set": {
            "result_set_id": last_result_set.get("result_set_id"),
            "query_summary": last_result_set.get("query_summary"),
            "count": last_result_set.get("count"),
            "entries": (last_result_set.get("entries") or [])[:8],
        }
        if last_result_set
        else None,
        "selected_entries": (state.get("selected_entries") or [])[:8],
        "last_evidence_pack": {
            "evidence_pack_id": last_evidence_pack.get("evidence_pack_id"),
            "question": last_evidence_pack.get("question"),
            "count": last_evidence_pack.get("count"),
            "tier_summary": last_evidence_pack.get("tier_summary") or {},
        }
        if last_evidence_pack
        else None,
        "budget_snapshot": state.get("budget_snapshot") or {},
        "recent_tool_trace": (state.get("recent_tool_trace") or [])[-8:],
        "last_runtime_notice": last_runtime_notice if last_runtime_notice else None,
        "last_stop_summary": last_stop_summary if last_stop_summary else None,
        "last_agent_error": last_agent_error if last_agent_error else None,
        "last_sufficiency": last_sufficiency if last_sufficiency else None,
        "last_scan_summary": (
            {
                "source": (last_scan.get("summary") or {}).get("source"),
                "topic": (last_scan.get("summary") or {}).get("topic"),
                "batch_id": (last_scan.get("summary") or {}).get("batch_id"),
                "scanned": (last_scan.get("summary") or {}).get("scanned"),
                "candidate_count": (last_scan.get("summary") or {}).get("candidate_count"),
                "relevant_count": (last_scan.get("summary") or {}).get("relevant_count"),
                "library_counts": (last_scan.get("summary") or {}).get("library_counts") or {},
                "skipped_count": (last_scan.get("summary") or {}).get("skipped_count"),
                "skipped_reasons": (last_scan.get("summary") or {}).get("skipped_reasons") or {},
                "skipped_examples": ((last_scan.get("summary") or {}).get("skipped_examples") or [])[:5],
                "scan_plan": (last_scan.get("summary") or {}).get("scan_plan") or {},
                "recommendations": (last_scan.get("summary") or {}).get("recommendations") or [],
            }
            if (last_scan.get("summary") or {})
            else None
        ),
        "working_notes": [_working_note_summary(item) for item in working_notes[-8:] if isinstance(item, dict)],
        "last_analysis_summary": {
            "topic": last_analysis_summary.get("topic"),
            "count": last_analysis_summary.get("count"),
            "clusters": (last_analysis_summary.get("clusters") or [])[:8],
            "journal_tier_distribution": (last_analysis_summary.get("journal_tier_distribution") or [])[:8],
            "priority_candidates": (last_analysis_summary.get("priority_candidates") or [])[:10],
        }
        if last_analysis_summary
        else None,
        "analysis_cache_summary": {
            "cache_id": analysis_cache.get("cache_id"),
            "topic": analysis_cache.get("topic"),
            "entry_count": analysis_cache.get("entry_count"),
            "source_scope": analysis_cache.get("source_scope"),
            "reused_from_cache_id": analysis_cache.get("reused_from_cache_id"),
            "parent_cache_id": analysis_cache.get("parent_cache_id"),
        }
        if analysis_cache
        else None,
        "pending_proposal": state.get("pending_proposal") or None,
        "last_execution": (
            {
                "proposal_id": (state.get("last_execution") or {}).get("proposal_id"),
                "action_type": (state.get("last_execution") or {}).get("action_type"),
                "status": (state.get("last_execution") or {}).get("status"),
                "job_id": (state.get("last_execution") or {}).get("job_id"),
                "batch_id": (state.get("last_execution") or {}).get("batch_id"),
                "mode": (state.get("last_execution") or {}).get("mode"),
                "selected_count": (state.get("last_execution") or {}).get("selected_count"),
                "tasks": ((state.get("last_execution") or {}).get("tasks") or [])[:6],
            }
            if state.get("last_execution")
            else None
        ),
    }
