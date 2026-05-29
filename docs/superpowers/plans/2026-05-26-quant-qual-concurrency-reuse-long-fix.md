# Quant Qual Concurrency Reuse Long Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make seven-step and four-step reading reuse the same stable concurrency architecture that now works for long-context reading on the new PostgreSQL server.

**Architecture:** Keep one file-level reading semaphore shared by long/quant/qual tasks, and add mode-specific inner concurrency caps so one batch cannot explode into too many DeepSeek requests. Keep `NullPool` for PostgreSQL async connections and avoid adding new event loops outside worker-thread boundaries.

**Tech Stack:** FastAPI, SQLAlchemy async, asyncpg, Python `threading.BoundedSemaphore`, `ThreadPoolExecutor`, `unittest`.

---

## Current State

Long-context reading has been stabilized with:

- `READING_FILE_CONCURRENCY=3`
- `LONG_DIMENSION_CONCURRENCY=6`
- file-level semaphore acquisition before `task_queue.mark_running(...)`
- PostgreSQL `NullPool` in `backend/db/session.py`
- queued-task cleanup via `task_queue.remove_queued(...)`

Seven-step and four-step reading already share the file-level semaphore after the 2026-05-26 hotfix, but their inner step concurrency is still hard-coded:

```python
ThreadPoolExecutor(max_workers=min(len(steps), 7))  # quant
ThreadPoolExecutor(max_workers=min(len(steps), 4))  # qual
```

This is acceptable for a single file, but in batch mode it becomes:

```text
3 running files * 7 quant steps = 21 simultaneous quant LLM calls
3 running files * 4 qual steps = 12 simultaneous qual LLM calls
```

The next change should make these caps explicit, configurable, and tested, matching long-context reading.

## Target Defaults

Use conservative defaults first:

```text
READING_FILE_CONCURRENCY=3
LONG_DIMENSION_CONCURRENCY=6
QUANT_STEP_CONCURRENCY=4
QUAL_STEP_CONCURRENCY=3
```

Rationale:

- Long-context reading is heavier per dimension, but tested successfully at file 3 x dimension 6.
- Quant has 7 fixed steps; 4 is fast enough while avoiding a 3 x 7 burst.
- Qual has 4 fixed steps; 3 keeps some parallelism without fully spiking each file.
- All values remain environment-variable configurable for server-specific tuning.

## Files

- Modify: `backend/routers/reading.py`
  - Add `QUANT_STEP_CONCURRENCY` and `QUAL_STEP_CONCURRENCY`.
  - Replace hard-coded quant/qual `ThreadPoolExecutor` caps.
  - Add logging at task start to record effective concurrency.
- Modify: `backend/tests/test_reading_concurrency.py`
  - Add tests for default quant/qual caps.
  - Add tests for invalid env parsing if module reload is introduced.
- Optional: `docs/NEW_SERVER_SQL_MAINTENANCE.md`
  - Document the four server tuning variables.

## Task 1: Extend Reading Concurrency Config Tests

**Files:**
- Modify: `backend/tests/test_reading_concurrency.py`

- [ ] **Step 1: Write failing tests for quant/qual defaults**

Add:

```python
def test_default_quant_and_qual_concurrency_are_conservative(self):
    self.assertEqual(reading.QUANT_STEP_CONCURRENCY, 4)
    self.assertEqual(reading.QUAL_STEP_CONCURRENCY, 3)
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m unittest backend.tests.test_reading_concurrency
```

Expected: fail with `AttributeError` for `QUANT_STEP_CONCURRENCY` and `QUAL_STEP_CONCURRENCY`.

## Task 2: Add Quant/Qual Config Constants

**Files:**
- Modify: `backend/routers/reading.py`

- [ ] **Step 1: Add constants near existing reading concurrency config**

Add:

```python
QUANT_STEP_CONCURRENCY = _parse_positive_int(os.getenv("QUANT_STEP_CONCURRENCY"), 4)
QUAL_STEP_CONCURRENCY = _parse_positive_int(os.getenv("QUAL_STEP_CONCURRENCY"), 3)
```

- [ ] **Step 2: Run config tests**

Run:

```powershell
python -m unittest backend.tests.test_reading_concurrency
```

Expected: pass.

## Task 3: Apply Quant/Qual Inner Caps

**Files:**
- Modify: `backend/routers/reading.py`

- [ ] **Step 1: Replace quant hard-coded cap**

Change:

```python
with ThreadPoolExecutor(max_workers=min(len(steps), 7)) as pool:
```

to:

```python
with ThreadPoolExecutor(max_workers=min(len(steps), QUANT_STEP_CONCURRENCY)) as pool:
```

- [ ] **Step 2: Replace qual hard-coded cap**

Change:

```python
with ThreadPoolExecutor(max_workers=min(len(steps), 4)) as pool:
```

to:

```python
with ThreadPoolExecutor(max_workers=min(len(steps), QUAL_STEP_CONCURRENCY)) as pool:
```

- [ ] **Step 3: Add concise start logging**

In `run_quant_task`, after `task_queue.mark_running(task_id)`:

```python
logger.info(
    "[quant:%s] concurrency file=%s steps=%s",
    task_id[:8],
    READING_FILE_CONCURRENCY,
    QUANT_STEP_CONCURRENCY,
)
```

In `run_qual_task`, after `task_queue.mark_running(task_id)`:

```python
logger.info(
    "[qual:%s] concurrency file=%s steps=%s",
    task_id[:8],
    READING_FILE_CONCURRENCY,
    QUAL_STEP_CONCURRENCY,
)
```

## Task 4: Verify Backend

**Files:**
- Verify only.

- [ ] **Step 1: Compile**

Run:

```powershell
python -m py_compile backend\routers\reading.py
```

Expected: exit code 0.

- [ ] **Step 2: Focused tests**

Run:

```powershell
python -m unittest backend.tests.test_reading_concurrency backend.tests.test_reading
```

Expected: pass.

- [ ] **Step 3: Regression check for `asyncio.run`**

Run:

```powershell
Select-String -Path backend\routers\references.py,backend\routers\reading.py,backend\routers\translation.py,backend\routers\filter.py -Pattern 'asyncio\.run\('
```

Expected: no output.

## Deployment Notes

Because the current new server still has a known duplicate router path issue, deploy `reading.py` to both paths until P15 is completed:

```powershell
scp backend\routers\reading.py root@8.162.14.154:/root/deep-reading-agent/backend/routers/reading.py
scp backend\routers\reading.py root@8.162.14.154:/root/deep-reading-agent/routers/reading.py
```

Then restart uvicorn and verify:

```bash
curl -sS -o /tmp/health.out -w '%{http_code} %{time_total}\n' http://127.0.0.1:18000/
```

Expected: `200`.

## Self-Review

- Spec coverage: quant and qual reuse the long-context concurrency approach through shared file-level throttling and mode-specific inner caps.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency: constants are `QUANT_STEP_CONCURRENCY` and `QUAL_STEP_CONCURRENCY`.
