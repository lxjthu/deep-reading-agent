from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.research_agent_runtime import (  # noqa: E402
    append_working_note,
    apply_execution_result_to_state,
    build_stop_summary,
    build_runtime_system_prompts,
    build_auto_continue_prompt,
    build_task_frame,
    enforce_tool_policy,
    normalize_tool_args,
    resolve_context_refs,
    summarize_state_for_ui,
    update_state_after_tool,
)


class ResearchAgentRuntimeTests(unittest.TestCase):
    def test_build_task_frame_detects_continuation_and_summary_intent(self) -> None:
        state = {
            "last_result_set": {
                "result_set_id": "rs-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                "count": 1,
            }
        }
        frame = build_task_frame("继续基于上一轮这些文献写一个对比综述", state)
        self.assertTrue(frame["continuation_ref"])
        self.assertEqual(frame["intent"], "summarize_topic")

    def test_build_task_frame_detects_english_continuation_from_previous_result_set(self) -> None:
        state = {
            "last_result_set": {
                "result_set_id": "rs-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                "count": 1,
            }
        }
        frame = build_task_frame(
            "Continue from the previous result set and expand these papers.",
            state,
        )
        self.assertTrue(frame["continuation_ref"])
        self.assertEqual(frame["intent"], "continue_result_set")
        self.assertTrue(frame["prefers_result_set_tools"])

    def test_build_task_frame_detects_english_synthesis_intent_on_previous_result_set(self) -> None:
        state = {
            "last_result_set": {
                "result_set_id": "rs-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                "count": 1,
            }
        }
        frame = build_task_frame(
            "Continue from the previous result set and synthesize the common themes and research gaps.",
            state,
        )
        self.assertTrue(frame["continuation_ref"])
        self.assertEqual(frame["intent"], "summarize_topic")
        self.assertTrue(frame["prefers_result_set_tools"])

    def test_build_task_frame_detects_english_execution_intent(self) -> None:
        frame = build_task_frame("Import these files and start batch reading in long mode.", {})
        self.assertEqual(frame["intent"], "start_job")
        self.assertTrue(frame["requires_write_proposal"])

    def test_build_task_frame_detects_english_status_intent(self) -> None:
        frame = build_task_frame("Check the job status and progress for the running batch.", {})
        self.assertEqual(frame["intent"], "check_status")

    def test_build_task_frame_detects_writing_style_intent(self) -> None:
        frame = build_task_frame("帮我分析宁健康这篇论文的引言写作风格", {})
        self.assertEqual(frame["intent"], "writing_style_analysis")
        self.assertTrue(frame["requires_local_search"])

    def test_normalize_tool_args_fills_writing_style_question_and_context(self) -> None:
        frame = build_task_frame("继续分析这些论文的方法写作风格", {"last_result_set": {"entries": [{"entry_id": "entry-1"}]}})
        resolved = {"status": "resolved", "entries": [{"entry_id": "entry-1", "title": "Paper A"}]}
        normalized = normalize_tool_args(
            "analyze_writing_style",
            {},
            task_frame=frame,
            resolved_context=resolved,
            state={},
        )
        self.assertEqual(normalized["question"], "继续分析这些论文的方法写作风格")
        self.assertEqual(normalized["entry_ids"], ["entry-1"])

    def test_runtime_prompts_recommend_writing_style_tool(self) -> None:
        frame = build_task_frame("帮我分析这篇文章理论部分怎么写", {})
        prompts = build_runtime_system_prompts(frame, {"status": "not_needed", "entries": []}, {})
        self.assertIn("analyze_writing_style", "\n".join(prompts))


    def test_build_task_frame_detects_research_idea_intent(self) -> None:
        frame = build_task_frame("基于这些文献帮我生成几个经济管理研究选题和机制假说", {})
        self.assertEqual(frame["intent"], "generate_research_ideas")
        self.assertTrue(frame["prefers_idea_lab_tools"])

    def test_runtime_prompt_recommends_idea_lab_tools(self) -> None:
        frame = build_task_frame("从这些论文里提取理论概念、机制和识别策略", {})
        prompts = build_runtime_system_prompts(frame, {"status": "not_needed", "entries": []}, {})
        combined = "\n".join(prompts)
        self.assertIn("extract_research_constructs", combined)
        self.assertIn("diagnose_research_gaps", combined)
        self.assertIn("generate_research_ideas", combined)
    def test_build_task_frame_detects_count_intent(self) -> None:
        frame = build_task_frame("我库里一共有多少篇已经精读的论文？", {})
        self.assertEqual(frame["intent"], "library_count")

    def test_build_task_frame_prefers_analysis_over_execution_for_unread_summary(self) -> None:
        frame = build_task_frame(
            "对没有启动精读的900篇做个分类总结，并列出优先精读的文献表格",
            {},
        )
        self.assertEqual(frame["intent"], "analyze_collection")
        self.assertFalse(frame["requires_write_proposal"])

    def test_build_task_frame_prefers_cached_analysis_for_subset_followup(self) -> None:
        state = {
            "analysis_cache": {
                "cache_id": "cache-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                "analysis_summary": {
                    "clusters": [{"label": "生成式人工智能 / GenAI", "count": 12}],
                },
            }
        }
        frame = build_task_frame(
            "专注看发表在 Economics Top 5 的生成式人工智能文献，并更详细做分类总结",
            state,
        )
        self.assertEqual(frame["intent"], "analyze_cached_collection")
        self.assertTrue(frame["continuation_ref"])
        self.assertTrue(frame["prefer_analysis_cache"])

    def test_build_task_frame_defaults_to_cached_analysis_for_generic_followup(self) -> None:
        state = {
            "analysis_cache": {
                "cache_id": "cache-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                "analysis_summary": {
                    "clusters": [{"label": "生成式人工智能 / GenAI", "count": 12}],
                },
            }
        }
        frame = build_task_frame(
            "更详细介绍每篇论文的主题和主要区别",
            state,
        )
        self.assertEqual(frame["intent"], "analyze_cached_collection")
        self.assertTrue(frame["continuation_ref"])
        self.assertTrue(frame["prefer_analysis_cache"])

    def test_build_task_frame_stops_using_cache_when_user_explicitly_changes_topic(self) -> None:
        state = {
            "analysis_cache": {
                "cache_id": "cache-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
            }
        }
        frame = build_task_frame(
            "换个话题，看看数字治理相关文献",
            state,
        )
        self.assertNotEqual(frame["intent"], "analyze_cached_collection")
        self.assertFalse(frame["prefer_analysis_cache"])
        self.assertTrue(frame["explicit_topic_shift"])

    def test_resolve_context_refs_prefers_selected_entries(self) -> None:
        state = {
            "selected_entries": [
                {"entry_id": "entry-1", "title": "Paper A"},
                {"entry_id": "entry-2", "title": "Paper B"},
            ],
            "last_result_set": {
                "result_set_id": "rs-1",
                "entries": [{"entry_id": "entry-3", "title": "Paper C"}],
                "count": 1,
            },
        }
        frame = build_task_frame("继续看这些文献", state)
        resolved = resolve_context_refs(frame, state)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["source"], "selected_entries")
        self.assertEqual([item["entry_id"] for item in resolved["entries"]], ["entry-1", "entry-2"])

    def test_normalize_tool_args_uses_resolved_entries_and_normalizes_star(self) -> None:
        state = {
            "last_result_set": {
                "result_set_id": "rs-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                "count": 1,
            }
        }
        frame = build_task_frame("继续基于上一轮这些文献总结", state)
        resolved = resolve_context_refs(frame, state)
        normalized_search = normalize_tool_args(
            "search_library",
            {"query": "*", "limit": 20},
            task_frame=frame,
            resolved_context=resolved,
            state=state,
        )
        normalized_pack = normalize_tool_args(
            "get_evidence_pack",
            {"question": ""},
            task_frame=frame,
            resolved_context=resolved,
            state=state,
        )
        self.assertEqual(normalized_search["query"], "")
        self.assertEqual(normalized_pack["entry_ids"], ["entry-1"])
        self.assertIn("上一轮", normalized_pack["question"])

    def test_normalize_tool_args_prefers_last_execution_job_for_status_checks(self) -> None:
        state = {
            "pending_proposal": {"proposal_id": "proposal-1", "action_type": "start_batch_reading", "status": "pending"},
            "last_execution": {
                "proposal_id": "proposal-1",
                "action_type": "start_batch_reading",
                "status": "executed",
                "tasks": [
                    {"job_id": "job-queued", "status": "queued", "file_name": "Paper A.pdf"},
                    {"job_id": "job-success", "status": "success", "file_name": "Paper B.pdf"},
                ],
            },
        }
        frame = build_task_frame("看看这个任务现在进度", state)
        normalized = normalize_tool_args(
            "get_job_status",
            {"job_id": "proposal-1"},
            task_frame=frame,
            resolved_context={},
            state=state,
        )
        self.assertEqual(normalized["job_id"], "job-queued")

    def test_normalize_tool_args_infers_cached_analysis_filters(self) -> None:
        state = {
            "analysis_cache": {
                "cache_id": "cache-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                "analysis_summary": {
                    "clusters": [{"label": "生成式人工智能 / GenAI", "count": 12}],
                },
            }
        }
        frame = build_task_frame(
            "专注看发表在 Economics Top 5 的未启动精读生成式人工智能文献",
            state,
        )
        normalized = normalize_tool_args(
            "filter_analysis_cache",
            {"topic": ""},
            task_frame=frame,
            resolved_context=resolve_context_refs(frame, state),
            state=state,
        )
        self.assertIn("Economics Top 5", normalized["journal_tier_labels"])
        self.assertEqual(normalized["cluster_labels"], ["生成式人工智能 / GenAI"])
        self.assertEqual(normalized["reading_status"], "none")
        self.assertEqual(normalized["max_entries"], 0)

    def test_enforce_tool_policy_blocks_external_without_explicit_user_request(self) -> None:
        frame = build_task_frame("看看这些文献的主要结论", {})
        block = enforce_tool_policy(
            "search_cnki",
            {"titles": ["Paper A"]},
            task_frame=frame,
            state={},
            resolved_context={},
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "external_consent_required")

    def test_enforce_tool_policy_blocks_per_entry_detail_for_result_set_summary(self) -> None:
        state = {
            "last_result_set": {
                "result_set_id": "rs-1",
                "entries": [
                    {"entry_id": "entry-1", "title": "Paper A"},
                    {"entry_id": "entry-2", "title": "Paper B"},
                ],
                "count": 2,
            }
        }
        frame = build_task_frame("继续基于上一轮这些文献总结共同结论", state)
        resolved = resolve_context_refs(frame, state)
        block = enforce_tool_policy(
            "get_entry_detail",
            {"entry_id": "entry-1"},
            task_frame=frame,
            state=state,
            resolved_context=resolved,
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "prefer_result_set_tools")

    def test_enforce_tool_policy_blocks_search_library_for_result_set_continuation(self) -> None:
        state = {
            "last_result_set": {
                "result_set_id": "rs-1",
                "entries": [
                    {"entry_id": "entry-1", "title": "Paper A"},
                    {"entry_id": "entry-2", "title": "Paper B"},
                ],
                "count": 2,
            }
        }
        frame = build_task_frame("继续基于上一轮这些文献总结共同问题", state)
        resolved = resolve_context_refs(frame, state)
        block = enforce_tool_policy(
            "search_library",
            {"query": "generative ai"},
            task_frame=frame,
            state=state,
            resolved_context=resolved,
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "prefer_contextual_result_set")

    def test_enforce_tool_policy_requires_context_when_continuation_has_no_result_set(self) -> None:
        frame = build_task_frame("继续分析上一轮这些文献", {})
        block = enforce_tool_policy(
            "get_evidence_pack",
            {"question": "总结"},
            task_frame=frame,
            state={},
            resolved_context={"status": "needs_clarification", "entries": []},
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "continuation_context_required")

    def test_enforce_tool_policy_requires_analysis_cache_before_filtering(self) -> None:
        frame = build_task_frame("只看顶刊文献", {})
        block = enforce_tool_policy(
            "filter_analysis_cache",
            {"topic": "只看顶刊文献"},
            task_frame=frame,
            state={},
            resolved_context={},
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "analysis_cache_required")

    def test_enforce_tool_policy_blocks_full_rescan_when_cached_analysis_exists(self) -> None:
        state = {
            "analysis_cache": {
                "cache_id": "cache-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
            }
        }
        frame = build_task_frame("专注看顶刊文献并做表格", state)
        block = enforce_tool_policy(
            "analyze_reading_candidates",
            {"topic": "专注看顶刊文献并做表格"},
            task_frame=frame,
            state=state,
            resolved_context=resolve_context_refs(frame, state),
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "prefer_analysis_cache_filter")

    def test_enforce_tool_policy_blocks_full_rescan_for_generic_followup_when_cache_exists(self) -> None:
        state = {
            "analysis_cache": {
                "cache_id": "cache-1",
                "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
            }
        }
        frame = build_task_frame("更详细介绍每篇论文的主题", state)
        block = enforce_tool_policy(
            "analyze_reading_candidates",
            {"topic": "更详细介绍每篇论文的主题"},
            task_frame=frame,
            state=state,
            resolved_context=resolve_context_refs(frame, state),
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "prefer_analysis_cache_filter")

    def test_update_state_after_tool_persists_result_set_and_budget(self) -> None:
        state = {"active_task_frame": {"raw_message": "列出库里的论文"}}
        next_state = update_state_after_tool(
            state,
            name="search_library",
            args={"query": "", "limit": 20},
            result={
                "count": 2,
                "entries": [
                    {"id": "entry-1", "title": "Paper A"},
                    {"id": "entry-2", "title": "Paper B"},
                ],
            },
        )
        self.assertEqual(next_state["last_result_set"]["count"], 2)
        self.assertEqual(len(next_state["selected_entries"]), 2)
        self.assertEqual(next_state["budget_snapshot"]["tool_counts"]["search_library"], 1)

    def test_duplicate_empty_calls_are_blocked(self) -> None:
        state = {"_runtime": {"recent_calls": [], "tool_counts": {}, "empty_tool_counts": {}}}
        for _ in range(2):
            state = update_state_after_tool(
                state,
                name="search_library",
                args={"query": "nonexistent"},
                result={"count": 0, "entries": []},
            )
        frame = build_task_frame("继续找", state)
        block = enforce_tool_policy(
            "search_library",
            {"query": "nonexistent"},
            task_frame=frame,
            state=state,
            resolved_context={},
        )
        self.assertIsNotNone(block)
        self.assertEqual(block["code"], "duplicate_tool_call_blocked")

    def test_runtime_prompts_and_ui_summary_include_result_set(self) -> None:
        state = {
            "last_result_set": {
                "result_set_id": "rs-1",
                "query_summary": "数字治理",
                "count": 2,
                "entries": [
                    {"entry_id": "entry-1", "title": "Paper A"},
                    {"entry_id": "entry-2", "title": "Paper B"},
                ],
            }
        }
        frame = build_task_frame("继续分析上一轮这些文献", state)
        resolved = resolve_context_refs(frame, state)
        prompts = build_runtime_system_prompts(frame, resolved, state)
        ui_state = summarize_state_for_ui(state)
        self.assertTrue(any("上一轮结果集" in prompt for prompt in prompts))
        self.assertTrue(any("结果集级工具" in prompt for prompt in prompts))
        self.assertEqual(ui_state["last_result_set"]["count"], 2)

    def test_runtime_prompts_recommend_batch_analysis_tool(self) -> None:
        frame = build_task_frame("对未精读文献做分类总结并给出优先精读表格", {})
        prompts = build_runtime_system_prompts(frame, {"status": "not_needed", "entries": []}, {})
        self.assertTrue(any("analyze_reading_candidates" in prompt for prompt in prompts))

    def test_runtime_prompts_and_ui_summary_include_last_execution_for_status_checks(self) -> None:
        state = {
            "last_execution": {
                "proposal_id": "proposal-1",
                "action_type": "start_batch_reading",
                "status": "executed",
                "batch_id": "batch-1",
                "tasks": [{"job_id": "job-1", "status": "queued", "file_name": "Paper A.pdf"}],
            }
        }
        frame = build_task_frame("检查当前批量任务的状态", state)
        prompts = build_runtime_system_prompts(frame, {"status": "not_needed", "entries": []}, state)
        ui_state = summarize_state_for_ui(state)
        self.assertTrue(any("最近一次已确认执行的任务摘要" in prompt for prompt in prompts))
        self.assertEqual(ui_state["last_execution"]["batch_id"], "batch-1")
        self.assertEqual(ui_state["last_execution"]["tasks"][0]["job_id"], "job-1")

    def test_ui_summary_includes_last_agent_error(self) -> None:
        ui_state = summarize_state_for_ui(
            {
                "last_agent_error": {
                    "code": "llm_timeout",
                    "message": "上游模型响应超时",
                    "stage": "llm_completion",
                    "retryable": True,
                }
            }
        )
        self.assertEqual(ui_state["last_agent_error"]["code"], "llm_timeout")
        self.assertTrue(ui_state["last_agent_error"]["retryable"])

    def test_update_state_after_tool_exposes_runtime_notice_to_ui(self) -> None:
        state = {"active_task_frame": {"raw_message": "继续总结"}}
        next_state = update_state_after_tool(
            state,
            name="search_library",
            args={"query": "generative ai"},
            result={
                "error": "inefficient_tool_path",
                "code": "prefer_contextual_result_set",
                "message": "请直接在上一轮结果集上继续。",
                "tool": "search_library",
                "suggested_tools": ["get_evidence_pack"],
                "recommendations": ["优先复用上一轮结果集。"],
            },
            blocked_by_policy=True,
        )
        ui_state = summarize_state_for_ui(next_state)
        self.assertEqual(ui_state["last_runtime_notice"]["code"], "prefer_contextual_result_set")
        self.assertEqual(ui_state["last_runtime_notice"]["suggested_tools"], ["get_evidence_pack"])
        self.assertEqual(ui_state["recent_tool_trace"][0]["status"], "blocked")
        self.assertTrue(ui_state["recent_tool_trace"][0]["blocked"])

    def test_update_state_after_tool_records_successful_trace_summary(self) -> None:
        state = {"active_task_frame": {"raw_message": "查一下生态产品价值实现相关文献"}}
        next_state = update_state_after_tool(
            state,
            name="research_search",
            args={"question": "生态产品价值实现", "entry_ids": ["entry-1", "entry-2"]},
            result={
                "count": 2,
                "entries": [
                    {"entry_id": "entry-1", "title": "Paper A"},
                    {"entry_id": "entry-2", "title": "Paper B"},
                ],
            },
        )
        trace = next_state["recent_tool_trace"][0]
        self.assertEqual(trace["tool"], "research_search")
        self.assertEqual(trace["status"], "success")
        self.assertTrue(trace["hit"])
        self.assertEqual(trace["arguments_summary"]["entry_ids_count"], 2)
        self.assertIn("返回 2 条结果", trace["result_summary"])

    def test_update_state_after_tool_records_count_trace_summary(self) -> None:
        next_state = update_state_after_tool(
            {},
            name="count_library",
            args={"query": "", "reading_status": "read"},
            result={"count": 42},
        )
        trace = next_state["recent_tool_trace"][0]
        self.assertEqual(trace["tool"], "count_library")
        self.assertEqual(trace["result_summary"], "共 42 篇文献")

    def test_append_working_note_and_analysis_summary_are_exposed_to_ui(self) -> None:
        state = append_working_note(
            {},
            {
                "kind": "batch_analysis",
                "topic": "未精读文献分类总结",
                "batch_index": 1,
                "processed_count": 100,
                "total_count": 900,
                "summary": "第一批主要集中在企业 AI 与平台治理。",
                "top_clusters": [{"label": "企业AI", "count": 32}],
                "priority_candidates": [{"title": "Paper A", "priority_score": 0.91}],
            },
            summary={
                "topic": "未精读文献分类总结",
                "count": 900,
                "clusters": [{"label": "企业AI", "count": 120}],
                "journal_tier_distribution": [{"label": "Economics Top 5", "count": 10}],
                "priority_candidates": [{"title": "Paper A", "priority_score": 0.91}],
            },
        )
        ui_state = summarize_state_for_ui(state)
        self.assertEqual(ui_state["working_notes"][0]["topic"], "未精读文献分类总结")
        self.assertEqual(ui_state["last_analysis_summary"]["count"], 900)
        self.assertEqual(ui_state["last_analysis_summary"]["clusters"][0]["label"], "企业AI")

    def test_update_state_after_tool_exposes_analysis_cache_summary(self) -> None:
        state = {"active_task_frame": {"raw_message": "专注看顶刊文献"}}
        next_state = update_state_after_tool(
            state,
            name="filter_analysis_cache",
            args={"topic": "专注看顶刊文献"},
            result={
                "count": 1,
                "working_notes": [
                    {
                        "kind": "cached_subset_analysis",
                        "topic": "专注看顶刊文献",
                        "batch_index": 1,
                        "processed_count": 1,
                        "total_count": 20,
                        "summary": "基于上一轮缓存继续筛选，当前命中 1/20 篇。",
                    }
                ],
                "analysis_summary": {
                    "topic": "专注看顶刊文献",
                    "count": 1,
                    "clusters": [{"label": "生成式人工智能 / GenAI", "count": 1}],
                    "journal_tier_distribution": [{"label": "Economics Top 5", "count": 1}],
                    "priority_candidates": [{"entry_id": "entry-1", "title": "Paper A", "priority_score": 0.9}],
                },
                "analysis_cache": {
                    "cache_id": "cache-2",
                    "topic": "专注看顶刊文献",
                    "entry_count": 1,
                    "source_scope": "analysis_cache_subset",
                    "reused_from_cache_id": "cache-1",
                    "parent_cache_id": "cache-1",
                    "entries": [{"entry_id": "entry-1", "title": "Paper A"}],
                },
            },
        )
        ui_state = summarize_state_for_ui(next_state)
        self.assertEqual(ui_state["analysis_cache_summary"]["cache_id"], "cache-2")
        self.assertEqual(ui_state["analysis_cache_summary"]["source_scope"], "analysis_cache_subset")
        self.assertEqual(ui_state["analysis_cache_summary"]["reused_from_cache_id"], "cache-1")


    def test_update_state_after_tool_stores_last_idea_lab_result(self) -> None:
        result = {
            "status": "ready",
            "topic": "digital capability",
            "constructs": [{"construct_id": "construct_1", "name": "digital capability"}],
            "gaps": [{"gap_id": "gap_1", "gap_type": "causal_identification"}],
            "ideas": [{"idea_id": "idea_1", "title": "Idea"}],
        }

        updated = update_state_after_tool(
            {},
            name="generate_research_ideas",
            args={"topic": "digital capability"},
            result=result,
        )
        ui_state = summarize_state_for_ui(updated)

        self.assertIn("last_idea_lab_result", updated)
        self.assertEqual(updated["last_idea_lab_result"]["topic"], "digital capability")
        self.assertEqual(updated["last_idea_lab_result"]["idea_count"], 1)
        self.assertEqual(ui_state["last_idea_lab_result"]["gap_count"], 1)
    def test_build_auto_continue_prompt_reuses_same_user_request(self) -> None:
        prompt = build_auto_continue_prompt(
            task_frame={"raw_message": "帮我分析这些论文的写作风格", "intent": "writing_style_analysis"},
            state={"last_result_set": {"count": 3}, "budget_snapshot": {"tool_counts": {"analyze_writing_style": 8}}},
            pass_index=1,
            max_passes=2,
        )
        self.assertIn("自动续跑", prompt)
        self.assertIn("帮我分析这些论文的写作风格", prompt)
        self.assertIn("不要要求用户重复输入", prompt)
        self.assertIn("3", prompt)

    def test_build_stop_summary_reports_auto_continue_attempts(self) -> None:
        summary = build_stop_summary(
            task_frame={"intent": "summarize_topic"},
            state={"last_result_set": {"count": 8}, "budget_snapshot": {"tool_counts": {"research_search": 2}}},
            reason="max_tool_rounds_reached",
            max_tool_rounds=8,
            auto_continue_attempts=2,
        )
        self.assertEqual(summary["auto_continue_attempts"], 2)
        self.assertIn("已自动续跑 2 次", summary["message"])

    def test_build_stop_summary_mentions_result_set_count(self) -> None:
        summary = build_stop_summary(
            task_frame={"intent": "summarize_topic"},
            state={"last_result_set": {"count": 8}, "budget_snapshot": {"tool_counts": {"research_search": 2}}},
            reason="max_tool_rounds_reached",
            max_tool_rounds=8,
        )
        self.assertEqual(summary["code"], "max_tool_rounds_reached")
        self.assertEqual(summary["result_set_count"], 8)
        self.assertIn("8", summary["message"])

    def test_apply_execution_result_to_state_clears_pending_proposal_and_persists_tasks(self) -> None:
        state = {
            "pending_proposal": {"proposal_id": "proposal-1", "action_type": "import_folder_and_start_reading", "status": "pending"}
        }
        next_state = apply_execution_result_to_state(
            state,
            proposal_id="proposal-1",
            action_type="import_folder_and_start_reading",
            proposal_status="executed",
            result={
                "mode": "long",
                "selected_count": 2,
                "batch": {
                    "batch_id": "batch-1",
                    "tasks": [
                        {"task_id": "job-1", "status": "queued", "file_name": "Paper A.pdf"},
                        {"task_id": "job-2", "status": "queued", "file_name": "Paper B.pdf"},
                    ],
                },
            },
        )
        self.assertIsNone(next_state["pending_proposal"])
        self.assertEqual(next_state["last_execution"]["batch_id"], "batch-1")
        self.assertEqual(next_state["last_execution"]["tasks"][0]["job_id"], "job-1")

    def test_apply_execution_result_to_state_supports_top_level_batch_tasks(self) -> None:
        next_state = apply_execution_result_to_state(
            {},
            proposal_id="proposal-2",
            action_type="start_batch_reading",
            proposal_status="executed",
            result={
                "batch_id": "batch-top",
                "tasks": [
                    {"task_id": "job-top-1", "status": "queued", "file_name": "Paper A.pdf"},
                    {"task_id": "job-top-2", "status": "queued", "file_name": "Paper B.pdf"},
                ],
            },
        )
        self.assertEqual(next_state["last_execution"]["batch_id"], "batch-top")
        self.assertEqual(next_state["last_execution"]["tasks"][1]["job_id"], "job-top-2")


if __name__ == "__main__":
    unittest.main()


