# Batch Reading Concurrency and Asyncpg Stability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make batch reading progress reliable on the new PostgreSQL server by preventing asyncpg connection reuse across thread event loops and limiting file-level reading concurrency.

**Architecture:** PostgreSQL async connections must not be pooled across different event loops, because background reading threads create their own loops while FastAPI runs on uvicorn's main loop. Use SQLAlchemy `NullPool` for PostgreSQL async engines, then add a real reading file concurrency gate so batch start can enqueue many files while only a small number run at once.

**Tech Stack:** FastAPI, SQLAlchemy async, asyncpg, PostgreSQL, Python `threading.BoundedSemaphore`, `unittest`.

---

## Files

- Modify: `backend/db/session.py`
  - For PostgreSQL URLs, use `sqlalchemy.pool.NullPool` instead of the default async pool.
  - Keep SQLite behavior unchanged.
- Modify: `backend/services/queue_manager.py`
  - Add a safe way to remove queued tasks when a queued task fails or is cancelled before it reaches running state.
- Modify: `backend/routers/reading.py`
  - Add environment-configurable reading file concurrency.
  - Acquire the reading file semaphore before `task_queue.mark_running(...)`.
  - Release the semaphore in `finally`.
  - Ensure exceptions before `mark_running(...)` remove the task from the queue.
  - Limit long-context dimension concurrency with an environment-configurable cap.
- Modify: `backend/tests/test_queue_manager.py`
  - Add tests for queued-task removal.
- Create: `backend/tests/test_session.py`
  - Add tests proving PostgreSQL uses `NullPool` and SQLite keeps connect args.
- Create: `backend/tests/test_reading_concurrency.py`
  - Add tests for concurrency defaults and environment parsing.

## Task 1: Queue Manager Cleanup

**Files:**
- Modify: `backend/services/queue_manager.py`
- Test: `backend/tests/test_queue_manager.py`

- [ ] **Step 1: Write failing queue cleanup tests**

Add tests:

```python
class TestRemoveQueued(unittest.TestCase):
    def setUp(self):
        self.qm = TaskQueueManager()

    def test_remove_queued_task_removes_from_queue(self):
        self.qm.enqueue("t1", user_id=1, task_type="long")
        self.qm.enqueue("t2", user_id=1, task_type="long")
        removed = self.qm.remove_queued("t1")
        self.assertTrue(removed)
        status = self.qm.get_queue_status()
        self.assertEqual(status["queue_length"], 1)
        self.assertEqual(status["queue_tasks"][0]["task_id"], "t2")

    def test_remove_queued_running_task_returns_false(self):
        self.qm.enqueue("t1", user_id=1, task_type="long")
        self.qm.mark_running("t1")
        removed = self.qm.remove_queued("t1")
        self.assertFalse(removed)
        self.assertEqual(self.qm.get_queue_status()["running_count"], 1)
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m unittest backend.tests.test_queue_manager.TestRemoveQueued
```

Expected: fail with `AttributeError: 'TaskQueueManager' object has no attribute 'remove_queued'`.

- [ ] **Step 3: Implement `remove_queued`**

Add:

```python
def remove_queued(self, task_id: str) -> bool:
    original_len = len(self._queue)
    self._queue = [entry for entry in self._queue if entry["task_id"] != task_id]
    removed = len(self._queue) != original_len
    if removed:
        logger.info("Task %s removed from queue", task_id)
    return removed
```

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m unittest backend.tests.test_queue_manager.TestRemoveQueued
```

Expected: pass.

## Task 2: PostgreSQL Async Engine Pool Safety

**Files:**
- Modify: `backend/db/session.py`
- Create: `backend/tests/test_session.py`

- [ ] **Step 1: Write failing pool selection tests**

Create test helpers that reload `db.session` with controlled `DATABASE_URL`.

```python
import importlib
import os
import sys
import unittest
from unittest.mock import patch


class TestSessionEngineOptions(unittest.TestCase):
    def reload_session(self, database_url: str):
        for name in ["db.session", "db"]:
            sys.modules.pop(name, None)
        with patch.dict(os.environ, {"DATABASE_URL": database_url}, clear=False):
            return importlib.import_module("db.session")

    def test_postgresql_uses_null_pool(self):
        session = self.reload_session("postgresql+asyncpg://user:pass@localhost/db")
        self.assertEqual(session.engine.pool.__class__.__name__, "NullPool")
        self.assertEqual(
            session.SYNC_DATABASE_URL,
            "postgresql+psycopg2://user:pass@localhost/db",
        )
        importlib.import_module("asyncio").run(session.engine.dispose())

    def test_sqlite_keeps_static_pool_behavior(self):
        session = self.reload_session("sqlite+aiosqlite:///tmp/test-session.sqlite")
        self.assertNotEqual(session.engine.pool.__class__.__name__, "NullPool")
        self.assertEqual(session.SYNC_DATABASE_URL, "sqlite:///tmp/test-session.sqlite")
        importlib.import_module("asyncio").run(session.engine.dispose())
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m unittest backend.tests.test_session
```

Expected: PostgreSQL test fails because current pool is not `NullPool`.

- [ ] **Step 3: Implement PostgreSQL `NullPool`**

In `backend/db/session.py`, import `NullPool` and set:

```python
elif DATABASE_URL.startswith("postgresql"):
    engine_kwargs.update(
        poolclass=NullPool,
        pool_pre_ping=True,
    )
```

Remove PostgreSQL `pool_size`, `max_overflow`, `pool_timeout`, and `pool_recycle` because they do not apply to `NullPool`.

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m unittest backend.tests.test_session
```

Expected: pass.

## Task 3: Reading Concurrency Configuration

**Files:**
- Modify: `backend/routers/reading.py`
- Create: `backend/tests/test_reading_concurrency.py`

- [ ] **Step 1: Write failing concurrency config tests**

Add tests for integer parsing:

```python
import unittest
from routers import reading


class TestReadingConcurrencyConfig(unittest.TestCase):
    def test_parse_positive_int_uses_default_for_invalid_values(self):
        self.assertEqual(reading._parse_positive_int("abc", 3), 3)
        self.assertEqual(reading._parse_positive_int("0", 3), 3)
        self.assertEqual(reading._parse_positive_int("-2", 3), 3)

    def test_parse_positive_int_accepts_positive_values(self):
        self.assertEqual(reading._parse_positive_int("5", 3), 5)
```

- [ ] **Step 2: Run red test**

Run:

```powershell
python -m unittest backend.tests.test_reading_concurrency
```

Expected: fail because `_parse_positive_int` does not exist.

- [ ] **Step 3: Implement config helpers and semaphores**

Add near imports/global constants:

```python
def _parse_positive_int(raw: object, default: int) -> int:
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


READING_FILE_CONCURRENCY = _parse_positive_int(os.getenv("READING_FILE_CONCURRENCY"), 3)
LONG_DIMENSION_CONCURRENCY = _parse_positive_int(os.getenv("LONG_DIMENSION_CONCURRENCY"), 6)
reading_file_semaphore = threading.BoundedSemaphore(READING_FILE_CONCURRENCY)
```

- [ ] **Step 4: Run green test**

Run:

```powershell
python -m unittest backend.tests.test_reading_concurrency
```

Expected: pass.

## Task 4: Apply File-Level Concurrency Gate

**Files:**
- Modify: `backend/routers/reading.py`

- [ ] **Step 1: Apply semaphore to `run_long_context_task`**

At function start, acquire `reading_file_semaphore` before creating the thread event loop and before `task_queue.mark_running(task_id)`.

Use this pattern:

```python
    acquired_slot = False
    loop = None
    try:
        reading_file_semaphore.acquire()
        acquired_slot = True
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        task_queue.mark_running(task_id)
```

In `except`, call:

```python
        if not acquired_slot:
            task_queue.remove_queued(task_id)
        else:
            task_queue.mark_completed(task_id)
```

In `finally`, close the loop if present and release semaphore if acquired.

- [ ] **Step 2: Apply the same pattern to `run_quant_task`**

Use the same `acquired_slot` and `loop is not None` checks.

- [ ] **Step 3: Apply the same pattern to `run_qual_task`**

Use the same `acquired_slot` and `loop is not None` checks.

- [ ] **Step 4: Reduce long dimension worker cap**

Change:

```python
workers = min(len(dims_to_analyze), 12)
```

to:

```python
workers = min(len(dims_to_analyze), LONG_DIMENSION_CONCURRENCY)
```

- [ ] **Step 5: Compile check**

Run:

```powershell
python -m py_compile backend\routers\reading.py backend\services\queue_manager.py backend\db\session.py
```

Expected: exit code 0.

## Task 5: Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m unittest backend.tests.test_queue_manager backend.tests.test_session backend.tests.test_reading_concurrency
```

Expected: pass.

- [ ] **Step 2: Run existing queue manager test command**

Run:

```powershell
python -m unittest backend.tests.test_queue_manager
```

Expected: pass.

- [ ] **Step 3: Check no accidental global `asyncio.run` regression**

Run:

```powershell
Select-String -Path backend\routers\references.py,backend\routers\reading.py,backend\routers\translation.py,backend\routers\filter.py -Pattern 'asyncio\.run\('
```

Expected: no output.

## Self-Review

- Spec coverage: addresses status 500 root cause by disabling PostgreSQL async pooling across event loops, and addresses runaway batch concurrency by gating file-level work and reducing dimension-level default concurrency.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: helper names are `_parse_positive_int`, `READING_FILE_CONCURRENCY`, `LONG_DIMENSION_CONCURRENCY`, and `reading_file_semaphore` throughout.
