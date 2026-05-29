# Library Existing Files Start Reading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users start long-context, seven-step, or four-step reading directly from already uploaded PDF/Markdown documents in the library, either through library multi-select actions or through AI assistant tool calls.

**Architecture:** Reuse existing `File` records and existing `/api/reading/batch/start` behavior. The library should expose which entries have readable files, map selected `BibEntry` rows to `source_file_id` or `markdown_source_file_id`, and call the same reading batch API used by folder upload. The AI assistant should accept library entry IDs, resolve them to owned file IDs, and then call the existing batch reading tool.

**Tech Stack:** FastAPI, SQLAlchemy async, React 19, Zustand/auth fetch helpers, existing `reading.BatchReadingRequest`, existing Agent proposal/confirmation flow.

---

## Current State

The data model already supports this feature:

- `BibEntry.source_file_id` points to an uploaded PDF or primary source file.
- `BibEntry.markdown_source_file_id` points to an uploaded Markdown file when available.
- `LibraryEntrySummary` already returns:
  - `source_file_id`
  - `source_file_name`
  - `source_file_type`
  - `markdown_source_file_id`
  - `markdown_source_file_name`
- Reading APIs already accept `file_id` and support batch:
  - `POST /api/reading/long/start`
  - `POST /api/reading/quant/start`
  - `POST /api/reading/qual/start`
  - `POST /api/reading/batch/start`
  - `GET /api/reading/batch/{batch_id}/status`
- Agent already has `tool_start_batch_reading(db, user, api_key, mode, file_ids, ...)`.

The missing pieces are UI and resolver ergonomics:

- Library entries are not currently multi-selectable for reading actions.
- Users cannot filter to "entries with readable PDF/MD" and start reading directly from the library.
- The AI assistant accepts `file_ids`, but user intent in the library is naturally expressed as selected `entry_ids` or "these library papers".

## Product Design

### Library UI

Add a selection mode to the library list:

- Checkbox per library entry.
- Select-all for current filtered page/list.
- Bulk action bar shown when one or more entries are selected.
- Reading actions:
  - "长文本精读"
  - "七步精读"
  - "四步精读"
  - optional "交给 AI 助手编排"

Eligibility:

- An entry is eligible if it has `markdown_source_file_id` or `source_file_id`.
- Prefer Markdown when both are available, because it is already text-like and cheaper to parse.
- If only PDF exists, use `source_file_id`.
- If neither exists, disable checkbox or mark as "无可读文件".

The bulk action should call existing reading conflict checks and batch start:

```text
selected entry IDs -> resolve file IDs -> /api/reading/batch/check-conflict -> user chooses skip/overwrite/incremental -> /api/reading/batch/start -> useBatchReadingTracker
```

### AI Assistant Flow

Add an AI tool path for selected library entries:

```text
entry_ids + mode -> resolve owned readable file_ids -> tool_start_batch_reading(...)
```

The confirmation dialog should say it is using existing library files, not uploading new files.

Suggested assistant action type:

```text
start_library_batch_reading
```

This keeps it distinct from the existing `start_batch_reading` action that expects raw `file_ids`.

## Backend Design

### Option A: Add Library Resolver Endpoint

Recommended.

Add a lightweight endpoint:

```text
POST /api/library/entries/resolve-reading-files
```

Request:

```json
{
  "entry_ids": ["..."],
  "prefer": "markdown"
}
```

Response:

```json
{
  "resolved": [
    {
      "entry_id": "...",
      "title": "...",
      "file_id": "...",
      "file_name": "...",
      "file_type": "markdown"
    }
  ],
  "unreadable": [
    {
      "entry_id": "...",
      "title": "...",
      "reason": "no_pdf_or_markdown"
    }
  ]
}
```

Then frontend calls existing reading batch APIs with `resolved[].file_id`.

Why this is recommended:

- Keeps `reading.py` focused on reading jobs.
- Keeps library ownership and entry-to-file resolution in `library.py`.
- Also reusable by AI assistant.

### Option B: Extend Reading Batch API to Accept Entry IDs

Not recommended for first implementation.

This would add `entry_ids` directly to `BatchReadingRequest`. It is convenient, but it mixes library selection concerns into the reading router and makes conflict responses more complex.

## Files

- Modify: `backend/routers/library.py`
  - Add request/response models.
  - Add `resolve_reading_files` endpoint.
  - Resolve each `BibEntry` under current user.
  - Prefer `markdown_source_file_id`, fallback to `source_file_id`.
  - Verify resolved `File` is owned by the same user and has type `pdf` or `markdown`.
- Modify: `backend/routers/agent.py`
  - Add tool function `tool_start_library_batch_reading`.
  - Add action handling for `start_library_batch_reading`.
  - Reuse library resolver logic or shared helper.
- Modify: `frontend/src/LibraryTab.tsx`
  - Add selection state for entries.
  - Add bulk action bar.
  - Add mode picker/actions for long/quant/qual.
  - Call resolver endpoint and reading batch APIs.
  - Show unreadable skipped count.
- Modify: `frontend/src/App.tsx`
  - Reuse or export `useBatchReadingTracker` if LibraryTab needs it.
  - Alternative: move batch tracker to `frontend/src/hooks/useBatchReadingTracker.ts`.
- Tests:
  - Add backend tests in `backend/tests/test_library.py` or a new `backend/tests/test_library_reading_files.py`.
  - Add/extend reading batch tests only if `BatchReadingRequest` changes.

## Task 1: Backend Library Resolver Tests

**Files:**
- Test: `backend/tests/test_library.py` or `backend/tests/test_library_reading_files.py`
- Modify: `backend/routers/library.py`

- [ ] **Step 1: Write failing test for resolving Markdown before PDF**

Create an owned `BibEntry` with both `source_file_id` and `markdown_source_file_id`, then call:

```python
response = client.post(
    "/api/library/entries/resolve-reading-files",
    headers=headers,
    json={"entry_ids": [entry_id], "prefer": "markdown"},
)
```

Expected response:

```python
self.assertEqual(response.status_code, 200)
body = response.json()
self.assertEqual(body["resolved"][0]["file_id"], markdown_file_id)
self.assertEqual(body["resolved"][0]["file_type"], "markdown")
self.assertEqual(body["unreadable"], [])
```

- [ ] **Step 2: Write failing test for unreadable entries**

Create an owned `BibEntry` with no source files. Expected:

```python
self.assertEqual(body["resolved"], [])
self.assertEqual(body["unreadable"][0]["reason"], "no_pdf_or_markdown")
```

- [ ] **Step 3: Run red tests**

Run:

```powershell
python -m unittest backend.tests.test_library_reading_files
```

Expected: fail because endpoint does not exist.

## Task 2: Backend Library Resolver Implementation

**Files:**
- Modify: `backend/routers/library.py`

- [ ] **Step 1: Add Pydantic models**

Add:

```python
class ResolveReadingFilesRequest(BaseModel):
    entry_ids: list[str] = Field(..., min_length=1, max_length=200)
    prefer: str = "markdown"


class ResolvedReadingFile(BaseModel):
    entry_id: str
    title: str
    file_id: str
    file_name: str
    file_type: str


class UnreadableEntry(BaseModel):
    entry_id: str
    title: str
    reason: str


class ResolveReadingFilesResponse(BaseModel):
    resolved: list[ResolvedReadingFile]
    unreadable: list[UnreadableEntry]
```

- [ ] **Step 2: Add helper**

Implement:

```python
async def resolve_entry_reading_files(
    db: AsyncSession,
    user: User,
    entry_ids: list[str],
    prefer: str = "markdown",
) -> tuple[list[dict], list[dict]]:
```

Rules:

- Query only `BibEntry.owner_user_id == user.id`.
- If `prefer == "markdown"`, candidate order is `[markdown_source_file_id, source_file_id]`.
- If `prefer == "pdf"`, candidate order is `[source_file_id, markdown_source_file_id]`.
- Accept only `File.owner_user_id == user.id` and `File.file_type in ("pdf", "markdown")`.
- Return unreadable entries for missing files, wrong owner, or unsupported type.

- [ ] **Step 3: Add endpoint**

Add:

```python
@router.post("/entries/resolve-reading-files", response_model=ResolveReadingFilesResponse)
async def resolve_reading_files(
    request: ResolveReadingFilesRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    resolved, unreadable = await resolve_entry_reading_files(db, user, request.entry_ids, request.prefer)
    return {"resolved": resolved, "unreadable": unreadable}
```

- [ ] **Step 4: Run green backend tests**

Run:

```powershell
python -m unittest backend.tests.test_library_reading_files
```

Expected: pass.

## Task 3: Agent Library Batch Tool

**Files:**
- Modify: `backend/routers/agent.py`

- [ ] **Step 1: Add action routing**

Where action proposals are dispatched, add:

```python
if proposal.action_type == "start_library_batch_reading":
    return await tool_start_library_batch_reading(db, user, api_key=api_key, **args)
```

- [ ] **Step 2: Add tool function**

Implement:

```python
async def tool_start_library_batch_reading(
    db: AsyncSession,
    user: User,
    *,
    api_key: str,
    mode: str,
    entry_ids: list[str],
    analysis_dims: list[str] | None = None,
    custom_question: str | None = None,
    extraction_method: str = "full",
    conflict_resolution: str = "skip",
    prefer: str = "markdown",
) -> dict[str, Any]:
    from routers.library import resolve_entry_reading_files

    resolved, unreadable = await resolve_entry_reading_files(db, user, entry_ids, prefer)
    file_ids = [item["file_id"] for item in resolved]
    if not file_ids:
        return {"error": "no_readable_library_files", "unreadable": unreadable}
    result = await tool_start_batch_reading(
        db,
        user,
        api_key=api_key,
        mode=mode,
        file_ids=file_ids,
        analysis_dims=analysis_dims,
        custom_question=custom_question,
        extraction_method=extraction_method,
        conflict_resolution=conflict_resolution,
    )
    if isinstance(result, dict):
        result["resolved_entries"] = resolved
        result["unreadable_entries"] = unreadable
    return result
```

- [ ] **Step 3: Add tests if agent action dispatch already has coverage**

If `backend/tests/test_agent.py` exists, add a dispatch test. If not, rely on library resolver tests and a manual agent flow test after implementation.

## Task 4: Frontend Batch Tracker Extraction

**Files:**
- Create: `frontend/src/hooks/useBatchReadingTracker.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/LibraryTab.tsx`

- [ ] **Step 1: Move `useBatchReadingTracker` from `App.tsx`**

Export:

```ts
export type BatchTaskSummary = {
  task_id: string
  file_name: string
  status: string
  progress: number
  stage: string
  download_url?: string
}

export type BatchState = {
  batchId: string | null
  total: number
  completed: number
  failed: number
  running: number
  queued: number
  tasks: BatchTaskSummary[]
  isBatchRunning: boolean
}

export function useBatchReadingTracker(storageKey = 'dra_batch_task_id') { ... }
```

- [ ] **Step 2: Update `App.tsx` imports**

Remove local hook definition and import:

```ts
import { useBatchReadingTracker } from './hooks/useBatchReadingTracker'
```

- [ ] **Step 3: Use separate storage key in LibraryTab**

In `LibraryTab.tsx`:

```ts
const batchTracker = useBatchReadingTracker('dra_library_batch_task_id')
```

This avoids clobbering ongoing batch state from Long/Quant/Qual tabs.

## Task 5: Library UI Multi-Select and Reading Actions

**Files:**
- Modify: `frontend/src/LibraryTab.tsx`

- [ ] **Step 1: Add selection state**

Add:

```ts
const [selectedEntryIds, setSelectedEntryIds] = useState<Set<string>>(new Set())
```

Add helpers:

```ts
const selectedEntries = entries.filter((entry) => selectedEntryIds.has(entry.id))
const readableSelectedCount = selectedEntries.filter((entry) => entry.markdown_source_file_id || entry.source_file_id).length
```

- [ ] **Step 2: Add checkboxes**

Render a checkbox per row/card. Disable it only when entry has no readable file if the UI chooses strict eligibility.

- [ ] **Step 3: Add bulk action bar**

Show when `selectedEntryIds.size > 0`.

Buttons:

- `长文本精读`
- `七步精读`
- `四步精读`

Each calls:

```ts
startReadingFromLibrary(mode)
```

- [ ] **Step 4: Implement resolver call**

```ts
const resolveRes = await apiFetch('/api/library/entries/resolve-reading-files', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ entry_ids: Array.from(selectedEntryIds), prefer: 'markdown' }),
})
```

Then use `resolved.map(item => item.file_id)`.

- [ ] **Step 5: Reuse conflict check and batch start**

Call:

```ts
POST /api/reading/batch/check-conflict
POST /api/reading/batch/start
```

Use same `conflict_resolution` behavior as existing batch upload tabs:

- default `skip`
- allow `overwrite`
- allow `incremental` only for long-context dimensions when applicable

- [ ] **Step 6: Show progress panel**

Reuse `batchTracker` result UI in a compact section above the library list.

## Task 6: Verification

**Files:**
- Verify only.

- [ ] **Backend tests**

Run:

```powershell
python -m unittest backend.tests.test_library_reading_files backend.tests.test_reading
```

Expected: pass.

- [ ] **Frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: pass.

- [ ] **Manual flow**

1. Upload several PDFs/Markdown files.
2. Confirm they appear in library with source file fields.
3. Select two readable entries in the library.
4. Click `长文本精读`.
5. Confirm batch progress appears and tasks leave 0%.
6. Repeat with `七步精读` and `四步精读`.
7. Ask AI assistant to start reading selected library entries.

## Deployment Notes

Because the new server currently has duplicate router path debt, if implementation touches `reading.py`, deploy it to both:

```powershell
scp backend\routers\reading.py root@8.162.14.154:/root/deep-reading-agent/backend/routers/reading.py
scp backend\routers\reading.py root@8.162.14.154:/root/deep-reading-agent/routers/reading.py
```

If implementation touches only `library.py` or `agent.py`, deploy to:

```powershell
scp backend\routers\library.py root@8.162.14.154:/root/deep-reading-agent/backend/routers/library.py
scp backend\routers\agent.py root@8.162.14.154:/root/deep-reading-agent/backend/routers/agent.py
```

After deployment, restart uvicorn and verify `http://8.162.14.154:18080/` returns `200`.

## Self-Review

- Spec coverage: covers direct library multi-select reading, existing PDF/MD reuse, and AI assistant library-entry reading.
- Placeholder scan: no TODO/TBD placeholders.
- Scope check: uses existing file/job/read APIs; no new database tables required.
