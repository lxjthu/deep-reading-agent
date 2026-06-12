# Reading Serial Cache and Source Evidence Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore same-paper reading dimensions to serial DeepSeek calls for cache reuse, then capture validated per-dimension original-text evidence during reading and expose it as hidden P0 evidence for Research Agent retrieval.

**Architecture:** Keep the current long-context strategy: one full-paper prompt prefix per paper, repeated dimension questions after that stable prefix. Remove same-paper dimension thread pools, preserve file-level queue/concurrency, and add a derived evidence table populated from DeepSeek-produced anchors only after the backend validates quotes against the locally extracted original text.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL 15+ full-text search, `pg_trgm`, DeepSeek via OpenAI-compatible SDK, Python `unittest`.

---

## Current Code Analysis

The user's concern is correct.

Current long-context caching design:

- `new_architecture/paper_cache.py:78-83` builds one fixed prompt prefix with `[论文信息]` and `[论文全文]`.
- `new_architecture/conversation_engine.py:95-109` places that paper prefix in a user message before each dimension question.
- `new_architecture/conversation_engine.py:101` states the intended cache strategy: when `max_history_turns=0`, no history is carried, so each step has the same cached prefix.
- `new_architecture/conversation_engine.py:191-196` logs `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`.

Current same-paper parallelism:

- Long-text reading creates one `PaperCache` and one `ConversationEngine` for the paper at `backend/routers/reading.py:1131-1137`, then runs dimensions through `ThreadPoolExecutor` at `backend/routers/reading.py:1235-1236`.
- Seven-step reading creates one `PaperCache` / `ConversationEngine` at `backend/routers/reading.py:1468-1469`, then runs steps through `ThreadPoolExecutor` at `backend/routers/reading.py:1488-1489`.
- Four-step reading creates one `PaperCache` / `ConversationEngine` at `backend/routers/reading.py:1687-1688`, then runs steps through `ThreadPoolExecutor` at `backend/routers/reading.py:1707-1708`.
- Empty-result retry also runs same-paper retry calls through a thread pool at `backend/routers/reading.py:1020`.

Why this is wrong for the current design:

- DeepSeek prompt cache is prefix-oriented. If multiple requests with the same full-paper prefix are sent concurrently, later calls may race before the first request has warmed the cache.
- The current thread pools share the same `ConversationEngine` and `PaperCache` instance. Even with `max_history_turns=0`, `engine.results` and `paper_cache.conversation_history` are mutated by multiple worker threads.
- The code intent is "same paper, same prefix, repeated dimension questions". That design should be serial inside a paper. Batch/file-level concurrency can remain separate.

Decision:

- Restore serial execution inside a single paper for long-text dimensions, seven-step prompts, four-step prompts, and empty-result retries.
- Preserve post-processing concurrency for metadata/reference extraction because those calls do not rely on the same full-paper cache prefix.
- Preserve file-level queue/concurrency unless a later performance/cost pass decides to reduce it.

---

## Scope

This plan has two implementation tracks.

Track A is a small behavior fix:

- Replace same-paper dimension thread pools with serial loops.
- Add tests proving serial helper behavior.
- Keep existing output and database schema unchanged.

Track B is a new evidence feature:

- During reading, ask DeepSeek to output hidden source evidence candidates alongside each dimension answer.
- Strip candidates from the displayed answer.
- Validate candidate quotes against local extracted paper text.
- Persist validated evidence by `reading_item`.
- Query that table as P0 local evidence.
- Add PostgreSQL FTS/trigram indexes for search reuse.

The two tracks can be implemented independently. Track A should ship first.

---

## File Structure

Modify:

- `backend/routers/reading.py`
  - Remove same-paper dimension thread pools.
  - Add a small serial execution helper.
  - Change empty-dimension retry to serial.
  - Pass source evidence records to finalization in Track B.

- `new_architecture/conversation_engine.py`
  - Add optional hidden evidence instruction support.
  - Preserve current return type for existing callers when evidence mode is disabled.
  - Store parsed evidence candidates in `TurnResult`.

- `backend/db/models.py`
  - Add `ReadingSourceEvidence`.

- `backend/migrations/versions/026_add_reading_source_evidence.py`
  - Add table and PostgreSQL indexes.
  - Enable `pg_trgm` on PostgreSQL.
  - Use ordinary indexes on SQLite for local tests.

- `backend/services/reading_source_evidence.py`
  - Parse hidden evidence blocks.
  - Validate quotes against local extracted text.
  - Normalize records for persistence.

- `backend/services/research_retrieval.py`
  - Search `ReadingSourceEvidence` and return validated rows as P0 evidence.

- `backend/services/data_portability.py`
  - Bump `CURRENT_SCHEMA_VERSION` to `026`.
  - Export/import `reading_source_evidence`.
  - Remap `reading_item_id`, `bib_entry_id`, `job_id`, and `source_file_id`.

Create tests:

- `backend/tests/test_reading_serial_execution.py`
- `backend/tests/test_reading_source_evidence.py`

Modify tests:

- `backend/tests/test_research_retrieval.py`
- `backend/tests/test_data_portability.py`
- `backend/tests/test_agent_tool_registry.py` only if tool schemas are later extended.

Docs to update after user-visible validation:

- `docs/RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`
- `docs/DATABASE_SCHEMA.md`
- `docs/README.md`

Per project rule, do not write completion-style docs before local and user verification.

---

## Task 1: Add Serial Execution Helper Tests

**Files:**

- Create: `backend/tests/test_reading_serial_execution.py`
- Modify later: `backend/routers/reading.py`

- [ ] **Step 1: Write failing tests for serial helper behavior**

Create `backend/tests/test_reading_serial_execution.py`:

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routers.reading import _run_units_serially


class ReadingSerialExecutionTests(unittest.TestCase):
    def test_run_units_serially_preserves_input_order(self) -> None:
        calls: list[str] = []

        def analyze(unit: str):
            calls.append(unit)
            return unit, f"answer-{unit}", None

        results, cancelled = _run_units_serially(
            ["研究问题", "理论框架", "识别策略"],
            analyze,
        )

        self.assertFalse(cancelled)
        self.assertEqual(calls, ["研究问题", "理论框架", "识别策略"])
        self.assertEqual(
            results,
            {
                "研究问题": "answer-研究问题",
                "理论框架": "answer-理论框架",
                "识别策略": "answer-识别策略",
            },
        )

    def test_run_units_serially_stops_on_cancelled_result(self) -> None:
        calls: list[str] = []

        def analyze(unit: str):
            calls.append(unit)
            if unit == "理论框架":
                return unit, None, "cancelled"
            return unit, f"answer-{unit}", None

        results, cancelled = _run_units_serially(
            ["研究问题", "理论框架", "识别策略"],
            analyze,
        )

        self.assertTrue(cancelled)
        self.assertEqual(calls, ["研究问题", "理论框架"])
        self.assertEqual(results, {"研究问题": "answer-研究问题"})

    def test_run_units_serially_reports_progress_after_each_success(self) -> None:
        progress: list[tuple[int, int, str, str | None]] = []

        def analyze(unit: str):
            return unit, f"answer-{unit}", None

        def on_progress(done: int, total: int, key: str, err: str | None) -> None:
            progress.append((done, total, key, err))

        results, cancelled = _run_units_serially(
            ["A", "B"],
            analyze,
            on_progress=on_progress,
        )

        self.assertFalse(cancelled)
        self.assertEqual(results, {"A": "answer-A", "B": "answer-B"})
        self.assertEqual(progress, [(1, 2, "A", None), (2, 2, "B", None)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new tests to verify failure**

Run:

```powershell
python -m unittest backend.tests.test_reading_serial_execution
```

Expected:

```text
ImportError: cannot import name '_run_units_serially'
```

---

## Task 2: Implement Serial Helper and Replace Same-Paper Thread Pools

**Files:**

- Modify: `backend/routers/reading.py`
- Test: `backend/tests/test_reading_serial_execution.py`

- [ ] **Step 1: Add the serial helper near `_check_and_retry_empty_dimensions`**

Add this helper before `_check_and_retry_empty_dimensions`:

```python
def _run_units_serially(
    units,
    analyze_one,
    *,
    on_progress=None,
    should_cancel=None,
):
    results = {}
    total = len(units)
    for done_count, unit in enumerate(units, start=1):
        if should_cancel and should_cancel():
            return results, True
        key, answer, err = analyze_one(unit)
        if err == "cancelled":
            return results, True
        if answer is not None:
            results[key] = answer
        if on_progress:
            on_progress(done_count, total, key, err)
    return results, False
```

This helper is intentionally small. It does not know about DeepSeek, task queues, or reading modes.

- [ ] **Step 2: Run helper tests**

Run:

```powershell
python -m unittest backend.tests.test_reading_serial_execution
```

Expected:

```text
OK
```

- [ ] **Step 3: Replace long-text dimension thread pool**

In `run_long_context_task`, replace the `ThreadPoolExecutor` block around `backend/routers/reading.py:1235-1251` with a serial loop using `_run_units_serially`.

Use this shape:

```python
def _on_long_progress(done_count, total, dim_key, err):
    tasks[task_id]["progress"] = 50 + int(40 * done_count / max(total, 1))
    if err:
        tasks[task_id]["logs"].append(f"⚠ {dim_key} 出错: {str(err)[:80]}")
    else:
        tasks[task_id]["logs"].append(f"✓ {dim_key} 完成")

new_results, cancelled = _run_units_serially(
    dims_to_analyze,
    _analyze_long_dim,
    on_progress=_on_long_progress,
    should_cancel=lambda: tasks[task_id].get("status") == "cancelled",
)
if cancelled:
    return
results.update(new_results)
```

Remove the `workers = min(...)` variable and the same-paper dimension `ThreadPoolExecutor`.

Do not remove the post-processing `ThreadPoolExecutor(max_workers=2)` used for metadata and references.

- [ ] **Step 4: Replace seven-step thread pool**

In `run_quant_task`, replace the `ThreadPoolExecutor` block around `backend/routers/reading.py:1488-1503` with:

```python
def _on_quant_progress(done_count, total, step_name, err):
    tasks[task_id]["progress"] = 15 + int(75 * done_count / max(total, 1))
    if err:
        tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(err)[:80]}")
        logger.warning("[quant:%s] %s 出错: %s", task_id[:8], step_name, err)
    else:
        answer = results.get(step_name, "")
        tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
        logger.info("[quant:%s] %s 完成, 回答长度=%d", task_id[:8], step_name, len(answer or ""))

results, cancelled = _run_units_serially(
    steps,
    lambda unit: _analyze_quant_step(unit[0], unit[1]),
    on_progress=_on_quant_progress,
    should_cancel=lambda: tasks[task_id].get("status") == "cancelled",
)
if cancelled:
    return
```

Before logging answer length, `results` is updated only after helper returns. If answer length logging must be exact during progress, use this local form instead:

```python
def _analyze_quant_unit(unit):
    step_name, prompt_key = unit
    key, answer, err = _analyze_quant_step(step_name, prompt_key)
    if answer is not None:
        tasks[task_id].setdefault("_last_step_answer_lengths", {})[key] = len(answer or "")
    return key, answer, err
```

Then use `_analyze_quant_unit` in `_run_units_serially` and read the length from `tasks[task_id]["_last_step_answer_lengths"]`.

- [ ] **Step 5: Replace four-step thread pool**

In `run_qual_task`, replace the `ThreadPoolExecutor` block around `backend/routers/reading.py:1707-1722` with:

```python
def _analyze_qual_unit(unit):
    step_name, prompt_key = unit
    key, answer, err = _analyze_qual_step(step_name, prompt_key)
    if answer is not None:
        tasks[task_id].setdefault("_last_step_answer_lengths", {})[key] = len(answer or "")
    return key, answer, err

def _on_qual_progress(done_count, total, step_name, err):
    tasks[task_id]["progress"] = 20 + int(70 * done_count / max(total, 1))
    if err:
        tasks[task_id]["logs"].append(f"⚠ {step_name} 出错: {str(err)[:80]}")
        logger.warning("[qual:%s] %s 出错: %s", task_id[:8], step_name, err)
    else:
        length = tasks[task_id].get("_last_step_answer_lengths", {}).get(step_name, 0)
        tasks[task_id]["logs"].append(f"✓ {step_name} 完成")
        logger.info("[qual:%s] %s 完成, 回答长度=%d", task_id[:8], step_name, length)

results, cancelled = _run_units_serially(
    steps,
    _analyze_qual_unit,
    on_progress=_on_qual_progress,
    should_cancel=lambda: tasks[task_id].get("status") == "cancelled",
)
if cancelled:
    return
```

- [ ] **Step 6: Compile reading router**

Run:

```powershell
python -m py_compile backend\routers\reading.py
```

Expected:

```text
no output
```

- [ ] **Step 7: Run focused tests**

Run:

```powershell
python -m unittest backend.tests.test_reading_serial_execution backend.tests.test_reading
```

Expected:

```text
OK
```

---

## Task 3: Make Empty-Dimension Retry Serial

**Files:**

- Modify: `backend/routers/reading.py`
- Modify: `backend/tests/test_reading_serial_execution.py`

- [ ] **Step 1: Add retry serialization test**

Append this test to `ReadingSerialExecutionTests`:

```python
    def test_empty_dimension_retry_runs_serially(self) -> None:
        from routers import reading

        task_id = "serial-retry-task"
        reading.tasks[task_id] = {
            "status": "running",
            "logs": [],
        }
        calls: list[str] = []

        def retry_fn(key: str) -> str:
            calls.append(key)
            return f"recovered {key}"

        try:
            results = reading._check_and_retry_empty_dimensions(
                {"A": "", "B": "", "C": "already ok"},
                task_id,
                retry_fn,
                max_retries=1,
            )
        finally:
            reading.tasks.pop(task_id, None)

        self.assertEqual(calls, ["A", "B"])
        self.assertEqual(results["A"], "recovered A")
        self.assertEqual(results["B"], "recovered B")
        self.assertEqual(results["C"], "already ok")
```

- [ ] **Step 2: Run test before implementation**

Run:

```powershell
python -m unittest backend.tests.test_reading_serial_execution
```

Expected before implementation:

```text
FAIL
```

The old implementation may not always fail deterministically because thread scheduling can preserve order by chance. If it passes once, run the test three times and inspect the code. The implementation still needs to remove the retry thread pool because it sends same-paper DeepSeek calls concurrently.

- [ ] **Step 3: Replace retry thread pool with serial loop**

In `_check_and_retry_empty_dimensions`, replace the `ThreadPoolExecutor` block with:

```python
for key in empty_keys:
    if tasks[task_id].get("status") == "cancelled":
        return results
    try:
        new_content = retry_fn(key)
        err = None
    except Exception as e:
        new_content = None
        err = str(e)

    if new_content and not _is_empty_result(new_content):
        results[key] = new_content
        tasks[task_id]["logs"].append(f"✓ [重试] {key} 完成")
    elif err:
        tasks[task_id]["logs"].append(f"⚠ [重试] {key} 失败: {str(err)[:80]}")
    else:
        tasks[task_id]["logs"].append(f"⚠ [重试] {key} 仍为空")
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest backend.tests.test_reading_serial_execution backend.tests.test_reading
```

Expected:

```text
OK
```

---

## Task 4: Add Hidden Source Evidence Parser and Validator

**Files:**

- Create: `backend/services/reading_source_evidence.py`
- Create: `backend/tests/test_reading_source_evidence.py`

- [ ] **Step 1: Write parser and validator tests**

Create `backend/tests/test_reading_source_evidence.py`:

```python
from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.reading_source_evidence import (
    SOURCE_EVIDENCE_BLOCK_END,
    SOURCE_EVIDENCE_BLOCK_START,
    split_answer_and_evidence,
    validate_source_evidence_candidates,
)


class ReadingSourceEvidenceTests(unittest.TestCase):
    def test_split_answer_and_evidence_extracts_hidden_json(self) -> None:
        raw = (
            "## 识别策略\n\n"
            "作者使用双重差分方法。\n\n"
            f"{SOURCE_EVIDENCE_BLOCK_START}\n"
            "{\"items\":[{\"claim\":\"DID method\",\"quote\":\"We use a difference-in-differences design.\",\"evidence_role\":\"method\"}]}\n"
            f"{SOURCE_EVIDENCE_BLOCK_END}"
        )

        answer, candidates, parse_error = split_answer_and_evidence(raw)

        self.assertIsNone(parse_error)
        self.assertEqual(answer.strip(), "## 识别策略\n\n作者使用双重差分方法。")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["quote"], "We use a difference-in-differences design.")

    def test_split_answer_and_evidence_returns_raw_answer_on_bad_json(self) -> None:
        raw = (
            "正文\n"
            f"{SOURCE_EVIDENCE_BLOCK_START}\n"
            "{bad json\n"
            f"{SOURCE_EVIDENCE_BLOCK_END}"
        )

        answer, candidates, parse_error = split_answer_and_evidence(raw)

        self.assertEqual(answer.strip(), "正文")
        self.assertEqual(candidates, [])
        self.assertIsNotNone(parse_error)

    def test_validate_source_evidence_candidates_marks_exact_match_as_p0(self) -> None:
        paper_text = "Introduction\nWe use a difference-in-differences design to estimate policy effects.\nConclusion"
        candidates = [
            {
                "claim": "作者使用DID识别政策影响",
                "quote": "We use a difference-in-differences design to estimate policy effects.",
                "evidence_role": "method",
                "section_hint": "Introduction",
            }
        ]

        records = validate_source_evidence_candidates(
            candidates,
            paper_text=paper_text,
            max_records=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["validation_status"], "exact")
        self.assertEqual(records[0]["source_tier"], "P0")
        self.assertEqual(records[0]["char_start"], len("Introduction\n"))
        self.assertGreater(records[0]["char_end"], records[0]["char_start"])

    def test_validate_source_evidence_candidates_does_not_promote_unmatched_quote(self) -> None:
        paper_text = "The actual paper text does not contain the generated sentence."
        candidates = [
            {
                "claim": "模型声称存在某个结论",
                "quote": "This exact quote is not in the paper.",
                "evidence_role": "finding",
            }
        ]

        records = validate_source_evidence_candidates(
            candidates,
            paper_text=paper_text,
            max_records=5,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["validation_status"], "unmatched")
        self.assertEqual(records[0]["source_tier"], "P2")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests before implementation**

Run:

```powershell
python -m unittest backend.tests.test_reading_source_evidence
```

Expected:

```text
ModuleNotFoundError: No module named 'services.reading_source_evidence'
```

- [ ] **Step 3: Implement parser and validator**

Create `backend/services/reading_source_evidence.py`:

```python
from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any


SOURCE_EVIDENCE_BLOCK_START = "<!--SOURCE_EVIDENCE_JSON"
SOURCE_EVIDENCE_BLOCK_END = "SOURCE_EVIDENCE_JSON-->"

SOURCE_EVIDENCE_INSTRUCTION = f"""

【隐藏原文证据要求】
在正常 Markdown 回答之后，追加一个 HTML 注释块。注释块不会展示给用户，只用于系统保存证据。
格式必须严格如下：
{SOURCE_EVIDENCE_BLOCK_START}
{{"items":[{{"claim":"一句中文概括","quote":"逐字摘自论文全文的原文片段","evidence_role":"method|data|finding|limitation|theory|background|contradiction","section_hint":"原文章节线索","page_hint":"页码线索或空字符串","confidence":"high|medium|low"}}]}}
{SOURCE_EVIDENCE_BLOCK_END}

规则：
1. quote 必须逐字来自上方论文全文，不得翻译、改写或补写。
2. 每个维度最多给 5 条最关键证据。
3. 如果找不到逐字原文证据，items 输出空数组。
4. 正文部分不要提及这个隐藏注释块。
"""


def split_answer_and_evidence(raw_answer: str) -> tuple[str, list[dict[str, Any]], str | None]:
    if SOURCE_EVIDENCE_BLOCK_START not in raw_answer:
        return raw_answer, [], None

    start = raw_answer.find(SOURCE_EVIDENCE_BLOCK_START)
    end = raw_answer.find(SOURCE_EVIDENCE_BLOCK_END, start)
    if end < 0:
        return raw_answer[:start].strip(), [], "missing_evidence_block_end"

    answer = raw_answer[:start].strip()
    block_start = start + len(SOURCE_EVIDENCE_BLOCK_START)
    block = raw_answer[block_start:end].strip()
    try:
        payload = json.loads(block)
    except json.JSONDecodeError as exc:
        return answer, [], f"invalid_json: {exc}"

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return answer, [], "items_not_list"

    candidates: list[dict[str, Any]] = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        if not quote:
            continue
        candidates.append(
            {
                "claim": str(item.get("claim") or "").strip(),
                "quote": quote,
                "evidence_role": str(item.get("evidence_role") or "support").strip(),
                "section_hint": str(item.get("section_hint") or "").strip(),
                "page_hint": str(item.get("page_hint") or "").strip(),
                "confidence": str(item.get("confidence") or "").strip(),
            }
        )
    return answer, candidates, None


def _normalize_for_match(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"(\w)-\s+(\w)", r"\1\2", text)
    return text


def _hash_text(text: str) -> str:
    return hashlib.sha256(_normalize_for_match(text).encode("utf-8")).hexdigest()


def _find_exact(paper_text: str, quote: str) -> tuple[int | None, int | None]:
    if not quote:
        return None, None
    pos = paper_text.find(quote)
    if pos >= 0:
        return pos, pos + len(quote)
    normalized_paper = _normalize_for_match(paper_text)
    normalized_quote = _normalize_for_match(quote)
    pos = normalized_paper.find(normalized_quote)
    if pos >= 0:
        return pos, pos + len(normalized_quote)
    return None, None


def _best_fuzzy_window(paper_text: str, quote: str) -> tuple[int | None, int | None, float]:
    normalized_quote = _normalize_for_match(quote)
    if len(normalized_quote) < 30:
        return None, None, 0.0
    window_size = max(len(normalized_quote) + 80, 240)
    step = max(40, window_size // 4)
    best_score = 0.0
    best_start: int | None = None
    best_end: int | None = None
    for start in range(0, max(len(paper_text) - 1, 1), step):
        window = paper_text[start : start + window_size]
        if not window:
            break
        score = SequenceMatcher(None, _normalize_for_match(window), normalized_quote).ratio()
        if score > best_score:
            best_score = score
            best_start = start
            best_end = min(len(paper_text), start + len(window))
    return best_start, best_end, round(best_score, 4)


def validate_source_evidence_candidates(
    candidates: list[dict[str, Any]],
    *,
    paper_text: str,
    max_records: int = 5,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for candidate in candidates:
        if len(records) >= max_records:
            break
        quote = str(candidate.get("quote") or "").strip()
        if len(quote) < 20:
            continue
        quote_hash = _hash_text(quote)
        if quote_hash in seen_hashes:
            continue
        seen_hashes.add(quote_hash)

        start, end = _find_exact(paper_text, quote)
        validation_status = "exact" if start is not None else "unmatched"
        match_score = 1.0 if start is not None else 0.0
        source_tier = "P0" if start is not None else "P2"

        if start is None:
            fuzzy_start, fuzzy_end, fuzzy_score = _best_fuzzy_window(paper_text, quote)
            if fuzzy_score >= 0.86:
                start = fuzzy_start
                end = fuzzy_end
                validation_status = "fuzzy"
                match_score = fuzzy_score
                source_tier = "P0"

        records.append(
            {
                "claim_text": str(candidate.get("claim") or "").strip(),
                "quote_text": quote,
                "quote_hash": quote_hash,
                "evidence_role": str(candidate.get("evidence_role") or "support").strip(),
                "section_hint": str(candidate.get("section_hint") or "").strip(),
                "page_label": str(candidate.get("page_hint") or "").strip() or None,
                "validation_status": validation_status,
                "match_score": match_score,
                "source_tier": source_tier,
                "char_start": start,
                "char_end": end,
                "metadata": {
                    "model_confidence": str(candidate.get("confidence") or "").strip(),
                },
            }
        )
    return records
```

- [ ] **Step 4: Run parser tests**

Run:

```powershell
python -m unittest backend.tests.test_reading_source_evidence
```

Expected:

```text
OK
```

---

## Task 5: Add Database Model and Migration for Reading Source Evidence

**Files:**

- Modify: `backend/db/models.py`
- Create: `backend/migrations/versions/026_add_reading_source_evidence.py`
- Modify: `backend/services/data_portability.py`

- [ ] **Step 1: Add ORM model**

Add this model after `ReadingItemEdit` in `backend/db/models.py`:

```python
class ReadingSourceEvidence(Base):
    __tablename__ = "reading_source_evidence"
    __table_args__ = (
        CheckConstraint(
            "source_version IN ('original','translated')",
            name="ck_rse_source_version",
        ),
        CheckConstraint(
            "source_tier IN ('P0','P1','P2','P3')",
            name="ck_rse_source_tier",
        ),
        CheckConstraint(
            "validation_status IN ('exact','fuzzy','unmatched')",
            name="ck_rse_validation_status",
        ),
        UniqueConstraint("reading_item_id", "quote_hash", name="uq_rse_item_quote"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bib_entry_id: Mapped[str] = mapped_column(ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    reading_item_id: Mapped[int] = mapped_column(ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False)
    source_file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("files.id"), nullable=True)
    source_version: Mapped[str] = mapped_column(String, nullable=False, default="original", server_default="original")
    source_tier: Mapped[str] = mapped_column(String, nullable=False, default="P0", server_default="P0")
    validation_status: Mapped[str] = mapped_column(String, nullable=False)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    item_key: Mapped[str] = mapped_column(String, nullable=False)
    item_label: Mapped[str] = mapped_column(String, nullable=False)
    evidence_role: Mapped[str] = mapped_column(String, nullable=False, default="support", server_default="support")
    claim_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    quote_hash: Mapped[str] = mapped_column(String, nullable=False)
    page_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    section_hint: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    heading_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_rse_owner", ReadingSourceEvidence.owner_user_id)
Index("idx_rse_bib", ReadingSourceEvidence.bib_entry_id)
Index("idx_rse_job", ReadingSourceEvidence.job_id)
Index("idx_rse_item", ReadingSourceEvidence.reading_item_id)
Index("idx_rse_tier_status", ReadingSourceEvidence.source_tier, ReadingSourceEvidence.validation_status)
Index("idx_rse_expires", ReadingSourceEvidence.expires_at)
```

Also add `ReadingSourceEvidence` to imports in files that need it later.

- [ ] **Step 2: Add migration**

Create `backend/migrations/versions/026_add_reading_source_evidence.py`:

```python
"""add reading source evidence

Revision ID: 026_add_reading_source_evidence
Revises: 025_add_bib_attachments
Create Date: 2026-06-12
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "026_add_reading_source_evidence"
down_revision: Union[str, None] = "025_add_bib_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reading_source_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bib_entry_id", sa.String(), sa.ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.String(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reading_item_id", sa.Integer(), sa.ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_file_id", sa.String(), sa.ForeignKey("files.id"), nullable=True),
        sa.Column("source_version", sa.String(), nullable=False, server_default="original"),
        sa.Column("source_tier", sa.String(), nullable=False, server_default="P0"),
        sa.Column("validation_status", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("item_label", sa.String(), nullable=False),
        sa.Column("evidence_role", sa.String(), nullable=False, server_default="support"),
        sa.Column("claim_text", sa.Text(), nullable=True),
        sa.Column("quote_text", sa.Text(), nullable=False),
        sa.Column("quote_hash", sa.String(), nullable=False),
        sa.Column("page_label", sa.String(), nullable=True),
        sa.Column("section_hint", sa.Text(), nullable=True),
        sa.Column("heading_path", sa.Text(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("source_version IN ('original','translated')", name="ck_rse_source_version"),
        sa.CheckConstraint("source_tier IN ('P0','P1','P2','P3')", name="ck_rse_source_tier"),
        sa.CheckConstraint("validation_status IN ('exact','fuzzy','unmatched')", name="ck_rse_validation_status"),
        sa.UniqueConstraint("reading_item_id", "quote_hash", name="uq_rse_item_quote"),
    )
    op.create_index("idx_rse_owner", "reading_source_evidence", ["owner_user_id"])
    op.create_index("idx_rse_bib", "reading_source_evidence", ["bib_entry_id"])
    op.create_index("idx_rse_job", "reading_source_evidence", ["job_id"])
    op.create_index("idx_rse_item", "reading_source_evidence", ["reading_item_id"])
    op.create_index("idx_rse_tier_status", "reading_source_evidence", ["source_tier", "validation_status"])
    op.create_index("idx_rse_expires", "reading_source_evidence", ["expires_at"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX idx_rse_quote_trgm "
            "ON reading_source_evidence USING gin (quote_text gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX idx_rse_claim_trgm "
            "ON reading_source_evidence USING gin (claim_text gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX idx_rse_fts_simple "
            "ON reading_source_evidence USING gin "
            "(to_tsvector('simple', coalesce(claim_text,'') || ' ' || coalesce(quote_text,'') || ' ' || coalesce(section_hint,'')))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_rse_fts_simple")
        op.execute("DROP INDEX IF EXISTS idx_rse_claim_trgm")
        op.execute("DROP INDEX IF EXISTS idx_rse_quote_trgm")
    op.drop_table("reading_source_evidence")
```

- [ ] **Step 3: Update data portability imports and schema version**

In `backend/services/data_portability.py`:

1. Import `ReadingSourceEvidence`.
2. Change:

```python
CURRENT_SCHEMA_VERSION = "025"
```

to:

```python
CURRENT_SCHEMA_VERSION = "026"
```

3. Add `ReadingSourceEvidence` immediately after `ReadingItem` in `EXPORT_TABLE_ORDER`.
4. Add `ReadingSourceEvidence` immediately before `ReadingItem` in `IMPORT_CLEAR_ORDER`.
5. Add FK remaps:

```python
"reading_source_evidence": {
    "bib_entry_id": "bib_entries",
    "job_id": "jobs",
    "reading_item_id": "reading_items",
    "source_file_id": "files",
},
```

- [ ] **Step 4: Compile models and migration**

Run:

```powershell
python -m py_compile backend\db\models.py backend\migrations\versions\026_add_reading_source_evidence.py backend\services\data_portability.py
```

Expected:

```text
no output
```

---

## Task 6: Persist Source Evidence With Reading Items

**Files:**

- Modify: `backend/routers/reading.py`
- Modify: `backend/tests/test_reading_source_evidence.py`

- [ ] **Step 1: Extend `finalize_reading_success` signature**

Change:

```python
async def finalize_reading_success(
    task_id: str,
    bib_entry_id: str,
    user_id: int,
    artifact_files: list[dict],
    reading_items: Optional[list[dict]] = None,
) -> None:
```

to:

```python
async def finalize_reading_success(
    task_id: str,
    bib_entry_id: str,
    user_id: int,
    artifact_files: list[dict],
    reading_items: Optional[list[dict]] = None,
    source_evidence_by_item_key: Optional[dict[str, list[dict]]] = None,
) -> None:
```

- [ ] **Step 2: Flush reading items and map item keys**

Replace the current `for item in reading_items or []` block with:

```python
inserted_items_by_key: dict[str, ReadingItem] = {}
for item in reading_items or []:
    reading_item = ReadingItem(
        owner_user_id=user_id,
        bib_entry_id=bib_entry_id,
        job_id=task_id,
        mode=item["mode"],
        section_type=item["section_type"],
        parent_key=item.get("parent_key"),
        item_key=item["item_key"],
        item_label=item["item_label"],
        sort_order=item.get("sort_order", 0),
        content=item["content"],
    )
    db.add(reading_item)
    await db.flush()
    inserted_items_by_key[reading_item.item_key] = reading_item
```

- [ ] **Step 3: Insert source evidence rows**

After the reading item insert loop, add:

```python
from db.models import ReadingSourceEvidence

source_file_id = bib_entry.markdown_source_file_id or bib_entry.source_file_id
for item_key, evidence_items in (source_evidence_by_item_key or {}).items():
    reading_item = inserted_items_by_key.get(item_key)
    if reading_item is None:
        continue
    for evidence in evidence_items:
        db.add(
            ReadingSourceEvidence(
                owner_user_id=user_id,
                bib_entry_id=bib_entry_id,
                job_id=task_id,
                reading_item_id=reading_item.id,
                source_file_id=source_file_id,
                source_version=evidence.get("source_version") or "original",
                source_tier=evidence.get("source_tier") or "P2",
                validation_status=evidence["validation_status"],
                mode=reading_item.mode,
                item_key=reading_item.item_key,
                item_label=reading_item.item_label,
                evidence_role=evidence.get("evidence_role") or "support",
                claim_text=evidence.get("claim_text"),
                quote_text=evidence["quote_text"],
                quote_hash=evidence["quote_hash"],
                page_label=evidence.get("page_label"),
                section_hint=evidence.get("section_hint"),
                heading_path=evidence.get("heading_path"),
                char_start=evidence.get("char_start"),
                char_end=evidence.get("char_end"),
                match_score=evidence.get("match_score"),
                metadata_json=json.dumps(evidence.get("metadata") or {}, ensure_ascii=False),
                expires_at=compute_expires_at(owner),
            )
        )
```

Ensure `json` is already imported in `backend/routers/reading.py`. It is currently imported near the top.

- [ ] **Step 4: Add persistence test**

Add a test that creates a job, bib entry, reading item payload, and `source_evidence_by_item_key`, then calls `finalize_reading_success` and verifies one `ReadingSourceEvidence` row exists. Use the same database setup style as `backend/tests/test_reading.py`.

The assertion must check:

```python
self.assertEqual(row.source_tier, "P0")
self.assertEqual(row.validation_status, "exact")
self.assertEqual(row.item_key, "long.overview")
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest backend.tests.test_reading_source_evidence backend.tests.test_reading
```

Expected:

```text
OK
```

---

## Task 7: Add Optional Evidence Mode to ConversationEngine

**Files:**

- Modify: `new_architecture/conversation_engine.py`
- Test: `backend/tests/test_reading_source_evidence.py`

- [ ] **Step 1: Extend `TurnResult`**

Change:

```python
@dataclass
class TurnResult:
    """单轮对话结果"""
    question: str
    answer: str
    dimension: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

to:

```python
@dataclass
class TurnResult:
    """单轮对话结果"""
    question: str
    answer: str
    dimension: Optional[str]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    source_evidence: Optional[list[dict]] = None
    source_evidence_parse_error: Optional[str] = None
```

- [ ] **Step 2: Import parser helpers**

Add near the top:

```python
try:
    from backend.services.reading_source_evidence import (
        SOURCE_EVIDENCE_INSTRUCTION,
        split_answer_and_evidence,
    )
except ImportError:
    from services.reading_source_evidence import (
        SOURCE_EVIDENCE_INSTRUCTION,
        split_answer_and_evidence,
    )
```

- [ ] **Step 3: Add evidence flag to `_build_messages`**

Change:

```python
def _build_messages(self, question: str, dimension: Optional[str] = None) -> List[Dict[str, str]]:
```

to:

```python
def _build_messages(
    self,
    question: str,
    dimension: Optional[str] = None,
    *,
    source_evidence_enabled: bool = False,
) -> List[Dict[str, str]]:
```

Before appending the final user message, add:

```python
if source_evidence_enabled:
    enhanced_question = f"{enhanced_question}\n{SOURCE_EVIDENCE_INSTRUCTION}"
```

- [ ] **Step 4: Add evidence flag to `ask`**

Change:

```python
def ask(self, question: str, dimension: Optional[str] = None) -> str:
```

to:

```python
def ask(
    self,
    question: str,
    dimension: Optional[str] = None,
    *,
    source_evidence_enabled: bool = False,
) -> str:
```

Call:

```python
messages = self._build_messages(
    question,
    dimension,
    source_evidence_enabled=source_evidence_enabled,
)
```

After receiving `raw_answer`, parse it:

```python
raw_answer = response.choices[0].message.content
if source_evidence_enabled:
    answer, source_evidence, parse_error = split_answer_and_evidence(raw_answer)
else:
    answer, source_evidence, parse_error = raw_answer, [], None
```

Store parsed evidence in `TurnResult`:

```python
turn = TurnResult(
    question=question,
    answer=answer,
    dimension=dimension,
    prompt_tokens=usage.prompt_tokens if usage else 0,
    completion_tokens=usage.completion_tokens if usage else 0,
    total_tokens=usage.total_tokens if usage else 0,
    source_evidence=source_evidence,
    source_evidence_parse_error=parse_error,
)
```

Return `answer`, not `raw_answer`.

- [ ] **Step 5: Add evidence flag to `analyze_dimension`**

Change:

```python
def analyze_dimension(
    self,
    dimension: str,
    custom_question: Optional[str] = None,
    dim_meta: Optional[Dict] = None,
) -> str:
```

to:

```python
def analyze_dimension(
    self,
    dimension: str,
    custom_question: Optional[str] = None,
    dim_meta: Optional[Dict] = None,
    *,
    source_evidence_enabled: bool = False,
) -> str:
```

Pass `source_evidence_enabled=source_evidence_enabled` into every `self.ask(...)` call inside this method.

- [ ] **Step 6: Add parser integration unit test**

In `backend/tests/test_reading_source_evidence.py`, add a small test for `split_answer_and_evidence`. Do not mock the OpenAI client in this task. The parser tests already cover the important contract without network calls.

- [ ] **Step 7: Compile**

Run:

```powershell
python -m py_compile new_architecture\conversation_engine.py backend\services\reading_source_evidence.py
```

Expected:

```text
no output
```

---

## Task 8: Collect and Validate Evidence During Reading

**Files:**

- Modify: `backend/routers/reading.py`

- [ ] **Step 1: Import validation helper**

Add near other service imports inside reading task functions or top-level:

```python
from services.reading_source_evidence import validate_source_evidence_candidates
```

Use the existing import fallback pattern if needed:

```python
try:
    from backend.services.reading_source_evidence import validate_source_evidence_candidates
except ImportError:
    from services.reading_source_evidence import validate_source_evidence_candidates
```

- [ ] **Step 2: Collect long-text evidence by dimension**

In `run_long_context_task`, create:

```python
source_evidence_by_dim: dict[str, list[dict]] = {}
```

Inside `_analyze_long_dim`, call:

```python
answer = engine.analyze_dimension(mapped_key, source_evidence_enabled=True)
```

For custom dimensions:

```python
answer = engine.analyze_dimension(
    dim_key,
    dim_meta=custom_dim_map[dim_key],
    source_evidence_enabled=True,
)
```

After each call, read the last result:

```python
last_turn = engine.results[-1] if engine.results else None
if last_turn and last_turn.source_evidence:
    source_evidence_by_dim[dim_key] = validate_source_evidence_candidates(
        last_turn.source_evidence,
        paper_text=paper_text,
        max_records=5,
    )
if last_turn and last_turn.source_evidence_parse_error:
    tasks[task_id]["logs"].append(
        f"⚠ {dim_key} 原文证据结构解析失败: {last_turn.source_evidence_parse_error}"
    )
```

Because Track A made the loop serial, reading `engine.results[-1]` is now safe.

- [ ] **Step 3: Map long-text evidence to reading item keys**

Before finalization:

```python
source_evidence_by_item_key: dict[str, list[dict]] = {}
for dim_key, evidence_items in source_evidence_by_dim.items():
    item_key = LONG_DIMENSION_KEYS.get(dim_key, f"long.{slugify_key_fragment(dim_key)}")
    source_evidence_by_item_key[item_key] = evidence_items
```

Pass it to `finalize_reading_success`:

```python
source_evidence_by_item_key=source_evidence_by_item_key,
```

- [ ] **Step 4: Collect seven-step evidence**

In `run_quant_task`, create:

```python
source_evidence_by_item_key: dict[str, list[dict]] = {}
```

Inside `_analyze_quant_step`, call:

```python
answer = engine.ask(prompt_content, source_evidence_enabled=True)
```

After the call:

```python
last_turn = engine.results[-1] if engine.results else None
if last_turn and last_turn.source_evidence:
    item_key = f"quant.step_{list(QUANT_PROMPT_KEYS.keys()).index(step_name) + 1}"
    source_evidence_by_item_key[item_key] = validate_source_evidence_candidates(
        last_turn.source_evidence,
        paper_text=paper_text,
        max_records=5,
    )
```

If `build_step_reading_items` uses a different item key format, inspect it and use that exact format. The evidence must bind to the top-level step item in the first version.

- [ ] **Step 5: Collect four-step evidence**

Apply the same pattern in `run_qual_task`, using the actual top-level item key generated by `build_step_reading_items(results, mode="qual")`.

- [ ] **Step 6: Keep unmatched evidence out of P0 search**

Do not discard unmatched evidence at persistence time. Store it with `source_tier="P2"` and `validation_status="unmatched"`. Retrieval will ignore it for P0 evidence but it remains auditable for debugging prompt quality.

- [ ] **Step 7: Compile and run focused tests**

Run:

```powershell
python -m py_compile backend\routers\reading.py new_architecture\conversation_engine.py backend\services\reading_source_evidence.py
python -m unittest backend.tests.test_reading_serial_execution backend.tests.test_reading_source_evidence backend.tests.test_reading
```

Expected:

```text
OK
```

---

## Task 9: Return Validated Source Evidence as P0 in Research Retrieval

**Files:**

- Modify: `backend/services/research_retrieval.py`
- Modify: `backend/tests/test_research_retrieval.py`

- [ ] **Step 1: Import model**

Add `ReadingSourceEvidence` to the existing model imports in `backend/services/research_retrieval.py`.

- [ ] **Step 2: Add related entry lookup by source evidence**

In `_load_entries`, after reading item related IDs, add:

```python
        source_evidence_ids = (
            await db.execute(
                select(ReadingSourceEvidence.bib_entry_id)
                .where(
                    ReadingSourceEvidence.owner_user_id == owner_user_id,
                    ReadingSourceEvidence.source_tier == "P0",
                    ReadingSourceEvidence.validation_status.in_(["exact", "fuzzy"]),
                    or_(
                        *[ReadingSourceEvidence.quote_text.ilike(like) for like in likes],
                        *[ReadingSourceEvidence.claim_text.ilike(like) for like in likes],
                        *[ReadingSourceEvidence.section_hint.ilike(like) for like in likes],
                    ),
                )
                .limit(limit)
            )
        ).scalars().all()
        related_ids.update(str(item) for item in source_evidence_ids)
```

This keeps current behavior before introducing PostgreSQL-specific query compilation.

- [ ] **Step 3: Collect source evidence before AI reading items**

In `_collect_entry_evidence`, query validated source evidence before the `if query.include_ai_notes` block:

```python
    source_evidence_rows = (
        await db.execute(
            select(ReadingSourceEvidence)
            .where(
                ReadingSourceEvidence.owner_user_id == owner_user_id,
                ReadingSourceEvidence.bib_entry_id == entry.id,
                ReadingSourceEvidence.source_tier == "P0",
                ReadingSourceEvidence.validation_status.in_(["exact", "fuzzy"]),
            )
            .order_by(ReadingSourceEvidence.reading_item_id, ReadingSourceEvidence.id)
        )
    ).scalars().all()
    for row in source_evidence_rows:
        text = "\n".join(part for part in [row.claim_text, row.quote_text, row.section_hint] if part)
        if _contains_any(text, terms):
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
```

- [ ] **Step 4: Add retrieval test**

Extend `backend/tests/test_research_retrieval.py` seed data with a `ReadingSourceEvidence` row linked to the existing `ReadingItem`.

Assert:

```python
self.assertTrue(any(item["source_kind"] == "source_evidence" for item in evidence))
source_index = next(i for i, item in enumerate(evidence) if item["source_kind"] == "source_evidence")
ai_index = next(i for i, item in enumerate(evidence) if item["source_kind"] == "reading_item")
self.assertLess(source_index, ai_index)
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest backend.tests.test_research_retrieval
```

Expected:

```text
OK
```

---

## Task 10: Add PostgreSQL FTS/Trigram Search Path

**Files:**

- Modify: `backend/services/research_retrieval.py`
- Test: `backend/tests/test_research_retrieval.py`

- [ ] **Step 1: Add dialect detection helper**

Add:

```python
def _db_dialect_name(db: AsyncSession) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else ""
```

- [ ] **Step 2: Add PostgreSQL source evidence query helper**

Add a helper that uses bound SQL text only for PostgreSQL:

```python
async def _search_source_evidence_postgres(
    db: AsyncSession,
    *,
    owner_user_id: int,
    terms: list[str],
    limit: int,
) -> list[str]:
    if not terms:
        return []
    query_text = " ".join(terms)
    rows = (
        await db.execute(
            sa.text(
                """
                SELECT bib_entry_id
                FROM reading_source_evidence
                WHERE owner_user_id = :owner_user_id
                  AND source_tier = 'P0'
                  AND validation_status IN ('exact', 'fuzzy')
                  AND (
                    to_tsvector('simple', coalesce(claim_text,'') || ' ' || coalesce(quote_text,'') || ' ' || coalesce(section_hint,'')) @@ plainto_tsquery('simple', :query_text)
                    OR quote_text % :query_text
                    OR claim_text % :query_text
                  )
                ORDER BY
                  ts_rank_cd(
                    to_tsvector('simple', coalesce(claim_text,'') || ' ' || coalesce(quote_text,'') || ' ' || coalesce(section_hint,'')),
                    plainto_tsquery('simple', :query_text)
                  ) DESC,
                  similarity(quote_text, :query_text) DESC
                LIMIT :limit
                """
            ),
            {
                "owner_user_id": owner_user_id,
                "query_text": query_text,
                "limit": limit,
            },
        )
    ).all()
    return [str(row[0]) for row in rows]
```

Add `import sqlalchemy as sa` at the top.

- [ ] **Step 3: Use PostgreSQL helper in `_load_entries`**

When dialect is PostgreSQL and terms exist, call `_search_source_evidence_postgres` and merge returned IDs into `related_ids`. Keep the existing `ILIKE` path for SQLite and as fallback.

- [ ] **Step 4: Do not make PostgreSQL SQL mandatory in unit tests**

Local tests use SQLite by default. Unit tests should verify fallback behavior. PostgreSQL index behavior is verified by server-side migration and smoke queries in deployment.

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest backend.tests.test_research_retrieval
```

Expected:

```text
OK
```

---

## Task 11: Data Portability Coverage

**Files:**

- Modify: `backend/services/data_portability.py`
- Modify: `backend/tests/test_data_portability.py`

- [ ] **Step 1: Add export/import test row**

In the existing data portability test fixture, create a `ReadingSourceEvidence` row after the `ReadingItem` row.

Use:

```python
ReadingSourceEvidence(
    owner_user_id=user.id,
    bib_entry_id=entry.id,
    job_id=job.id,
    reading_item_id=reading_item.id,
    source_file_id=file.id,
    source_version="original",
    source_tier="P0",
    validation_status="exact",
    mode="long",
    item_key="long.overview",
    item_label="研究问题",
    evidence_role="method",
    claim_text="作者使用DID",
    quote_text="We use a difference-in-differences design.",
    quote_hash="hash-did",
    match_score=1.0,
    metadata_json="{}",
)
```

- [ ] **Step 2: Assert export contains table**

After export, assert the exported manifest/table payload includes `reading_source_evidence`.

- [ ] **Step 3: Assert import remaps reading item id**

After import, query the imported `ReadingSourceEvidence` row and assert:

```python
self.assertEqual(row.item_key, "long.overview")
self.assertNotEqual(row.reading_item_id, old_reading_item_id)
self.assertEqual(row.quote_text, "We use a difference-in-differences design.")
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest backend.tests.test_data_portability
```

Expected:

```text
OK
```

---

## Task 12: Manual Verification Plan

**Files:**

- No code changes.
- Use local app and production after explicit deployment approval.

- [ ] **Step 1: Local serial behavior verification**

Start backend and frontend locally, then run one long-text reading on a paper with at least 3 dimensions.

Expected task logs:

```text
✓ 研究问题 完成
✓ 理论框架 完成
✓ 识别策略 完成
```

The logs should appear in dimension order, not in completion-race order.

- [ ] **Step 2: Cache behavior observation**

Watch backend console logs from `ConversationEngine.ask`.

Expected:

```text
[Cache] hit=...
```

The first dimension may have high miss tokens. Later dimensions in the same paper should show materially higher hit tokens if DeepSeek cache is active.

- [ ] **Step 3: Evidence persistence verification**

After a successful reading, query local DB:

```sql
SELECT item_key, source_tier, validation_status, left(quote_text, 80)
FROM reading_source_evidence
ORDER BY id
LIMIT 20;
```

Expected:

```text
rows exist for the reading job
validated rows have source_tier = P0 and validation_status in exact/fuzzy
unmatched rows have source_tier = P2
```

- [ ] **Step 4: Retrieval verification**

Ask the Research Agent a question that matches a stored source quote.

Expected:

- `research_search` or `get_evidence_pack` returns `source_kind=source_evidence`.
- The evidence tier summary includes P0.
- P0 source evidence ranks before P2 `reading_item` summaries.

- [ ] **Step 5: PostgreSQL migration verification on server**

Only after user approval for deployment:

```bash
cd /root/deep-reading-agent/backend
source ../venv/bin/activate
python -m alembic upgrade head
```

Then verify:

```sql
SELECT extname FROM pg_extension WHERE extname = 'pg_trgm';
\d reading_source_evidence
\di idx_rse*
```

Expected:

```text
pg_trgm exists
reading_source_evidence exists
GIN indexes exist
```

---

## Task 13: Documentation After Verification

**Files:**

- Modify after user-visible validation: `docs/RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`
- Modify after user-visible validation: `docs/DATABASE_SCHEMA.md`
- Modify after user-visible validation: `docs/README.md`

- [ ] **Step 1: Update runtime roadmap**

Add a new implemented or planned slice:

```markdown
### Phase 2.5: Serial Cached Reading and Source Evidence Index

Goal: preserve DeepSeek prompt cache efficiency by running dimensions serially within a paper, then store validated original-text evidence anchors as hidden P0 retrieval evidence.

Behavior:
- Same-paper long/quant/qual dimensions run serially.
- Reading answers can include hidden source evidence candidates.
- Backend validates quotes against local extracted text before promoting them to P0.
- Research Agent retrieval can use validated evidence as P0 source evidence.
- PostgreSQL uses `pg_trgm` and FTS indexes for reuse.
```

- [ ] **Step 2: Update database schema doc**

Add `reading_source_evidence` table with fields, constraints, and export/import behavior.

- [ ] **Step 3: Update docs README**

Add the roadmap/schema doc changes to the documentation navigation if needed.

- [ ] **Step 4: Run doc-adjacent checks**

Run:

```powershell
git diff --check
```

Expected:

```text
no output
```

---

## Risk Controls

- Same-paper serial execution increases wall-clock time per paper but should reduce prompt cache misses and avoids shared `ConversationEngine` mutation races.
- File-level reading concurrency remains. If production cost is still high, reduce `READING_FILE_CONCURRENCY` separately.
- Evidence extraction must never block reading success. Missing evidence blocks should be logged and ignored.
- DeepSeek-provided quotes are not P0 until backend validation succeeds.
- PostgreSQL FTS/trigram improves reuse after evidence exists. It is not the primary way to discover original evidence during first reading.
- PDF extraction currently flattens text via `extractor.py`; page labels may be unavailable in first version. Store `page_hint` from model as a hint, but rely on `char_start` / `char_end` for validated local evidence.
- Because `reading_source_evidence` is expensive to regenerate, include it in `.dra` export/import instead of treating it as disposable cache.

---

## Verification Commands

Run before commit:

```powershell
python -m py_compile backend\routers\reading.py new_architecture\conversation_engine.py backend\services\reading_source_evidence.py backend\db\models.py backend\services\research_retrieval.py backend\services\data_portability.py
python -m unittest backend.tests.test_reading_serial_execution backend.tests.test_reading_source_evidence backend.tests.test_research_retrieval backend.tests.test_data_portability backend.tests.test_reading
git diff --check
```

Expected:

```text
all unittest modules pass
py_compile emits no output
git diff --check emits no output
```

---

## Commit Plan

Commit Track A separately:

```bash
git add backend/routers/reading.py backend/tests/test_reading_serial_execution.py
git commit -m "fix: run same-paper reading dimensions serially"
```

Commit Track B separately:

```bash
git add backend/db/models.py backend/migrations/versions/026_add_reading_source_evidence.py backend/services/reading_source_evidence.py new_architecture/conversation_engine.py backend/routers/reading.py backend/services/research_retrieval.py backend/services/data_portability.py backend/tests/test_reading_source_evidence.py backend/tests/test_research_retrieval.py backend/tests/test_data_portability.py
git commit -m "feat: index validated reading source evidence"
```

Docs commit after user-visible verification:

```bash
git add docs/RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md docs/DATABASE_SCHEMA.md docs/README.md
git commit -m "docs: record reading source evidence indexing"
```

---

## Self-Review

Spec coverage:

- Same-paper long/quant/qual serial execution is covered by Tasks 1-3.
- DeepSeek long-context evidence extraction is covered by Tasks 4, 7, and 8.
- Backend quote validation before P0 promotion is covered by Task 4.
- Per-dimension storage bound to `reading_items` is covered by Tasks 5-6.
- Research Agent retrieval as P0 evidence is covered by Tasks 9-10.
- PostgreSQL FTS/trigram direction is covered by Tasks 5 and 10.
- Data portability is covered by Task 11.

Placeholder scan:

- The plan uses concrete file paths, commands, and expected outputs.
- The implementation deliberately avoids broad refactors and keeps Track A independent from Track B.

Type consistency:

- Evidence records use `source_evidence_by_item_key: dict[str, list[dict]]` through reading finalization.
- Stored rows map to `ReadingSourceEvidence`.
- Retrieval exposes stored rows as `source_kind="source_evidence"` and `source_tier="P0"` only when validated.
