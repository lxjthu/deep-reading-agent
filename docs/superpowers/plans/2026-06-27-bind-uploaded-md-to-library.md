# Bind Uploaded Markdown Files To Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the 261 already-uploaded OCR Markdown files for production user `owner_user_id=5` into the user's library without moving files or overwriting user-curated metadata.

**Architecture:** Add a one-time, resumable backend repair script that parses Markdown YAML frontmatter, matches each file to an owned `BibEntry` when possible, and creates a new `BibEntry` when the user's library has no match. The script runs in dry-run mode first and writes an audit report before any database mutation.

**Tech Stack:** FastAPI project models, SQLAlchemy async session, PostgreSQL production database, PyYAML/frontmatter parsing, existing `db.utils` metadata helpers.

---

## Current Evidence

- Production files are present under `/root/deep-reading-agent/_uploads/5/`.
- Production `files` table has 261 Markdown rows for `owner_user_id=5`, all created on `2026-06-27 14:39:20` through `2026-06-27 14:41:51`.
- These rows have original names like `生态产品价值实现文献/..._ocr.md`, but disk filenames are UUIDs.
- The Markdown files contain YAML frontmatter with useful bibliography fields: `title`, `authors`, `journal`, `year`, `issue`, `volume`, `start_page`, `end_page`, `doi`, `abstract`, `citation`, `bib_idx`, `source_file`, `tags`.
- The current user's library has `0` `bib_entries`, so the main repair path is to create library entries from Markdown metadata. The matching code still needs to exist because this repair script should be safe if rerun after some entries are created.
- The upload batch row `64432f84-1edd-4ff3-9624-5ecf48322eda` says `total_files=200`, `succeeded=0`, `failed=200`, `status=failed`, but the actual 261 `files` rows are already persisted with `batch_id=NULL`. This plan does not rely on the stale batch status.

## Files

- Create: `backend/scripts/backfill_uploaded_markdown_library.py`
  - One-time repair script with `--dry-run` default.
  - Parses frontmatter, computes match decisions, creates or links `BibEntry` rows only when `--apply` is passed.
- Create: `backend/tests/test_backfill_uploaded_markdown_library.py`
  - Unit tests for frontmatter parsing, matching priority, duplicate handling, dry-run non-mutation, and apply mutation.
- Modify: none in production app routes for this repair.

## Matching Rules

For each candidate `File`:

1. Candidate scope:
   - `File.owner_user_id == 5`
   - `File.file_type == "markdown"`
   - `File.storage_path LIKE "_uploads/5/%"`
   - `File.original_name ILIKE "%_ocr.md"` or frontmatter has `extractor` / `source_file`
   - `File.created_at` between `2026-06-27 14:39:00` and `2026-06-27 14:42:30`

2. Parse metadata:
   - `title`: frontmatter `title`, fallback to original filename stem with folder prefix and `_ocr` removed.
   - `authors`: frontmatter list or split string.
   - `doi`: `db.utils.normalize_doi`.
   - `year`: integer year.
   - `journal`, `abstract`, `volume`, `issue`.
   - `pages`: `start_page-end_page` when both exist, otherwise whichever page field exists.
   - `keywords_json`: frontmatter `keywords` or `tags`.
   - `source_db`: `md_extracted`.
   - `source_file_id`: the Markdown `File.id`.
   - `markdown_source_file_id`: the Markdown `File.id`.
   - `reading_status`: `has_pdf`, matching existing app behavior for Markdown full text.
   - `metadata_completeness`: reuse `compute_metadata_completeness`.
   - `dedup_key`: reuse `compute_dedup_key`.

3. Match existing owned `BibEntry` in this order:
   - DOI exact match after normalization.
   - Exact dedup key match.
   - Exact normalized title match when year is compatible.
   - High title similarity `>= 0.93` when year is compatible and first author is compatible when both sides have authors.

4. Conflict handling:
   - If multiple existing entries match the same file, skip and write `ambiguous_existing_match` to the report.
   - If multiple Markdown files produce the same dedup key, choose the most complete candidate, then the larger file size, and skip the others with `duplicate_markdown_candidate`.
   - Never overwrite an existing `markdown_source_file_id`; skip with `already_has_markdown`.
   - Only fill empty metadata fields on matched existing entries. Do not replace non-empty title/authors/year/doi/journal/abstract.

5. Creation rule:
   - If no existing owned entry matches and the Markdown has a title, create a new `BibEntry`.
   - If title is missing, skip with `missing_title`.

## Tasks

### Task 1: Add Metadata Parser And Match Planner

**Files:**
- Create: `backend/scripts/backfill_uploaded_markdown_library.py`
- Test: `backend/tests/test_backfill_uploaded_markdown_library.py`

- [ ] Write tests for parsing YAML frontmatter into normalized metadata.
- [ ] Implement `parse_markdown_metadata(path: Path, original_name: str) -> MarkdownMetadata`.
- [ ] Write tests for DOI, dedup key, exact title, and high-title matching priority.
- [ ] Implement `plan_bindings(files, existing_entries) -> BackfillPlan`.
- [ ] Run:
  - `python -m unittest backend.tests.test_backfill_uploaded_markdown_library`
  - Expected: pass.

### Task 2: Add Dry-Run Report

**Files:**
- Modify: `backend/scripts/backfill_uploaded_markdown_library.py`
- Test: `backend/tests/test_backfill_uploaded_markdown_library.py`

- [ ] Add CLI arguments:
  - `--owner-user-id 5`
  - `--storage-prefix _uploads/5/`
  - `--created-after "2026-06-27T14:39:00"`
  - `--created-before "2026-06-27T14:42:30"`
  - `--report-path /tmp/md-library-backfill-user5.json`
  - `--dry-run` default
  - `--apply` required for writes
- [ ] Dry-run must not commit database changes.
- [ ] Report fields:
  - `candidate_files`
  - `parsed`
  - `would_create_entries`
  - `would_link_existing_entries`
  - `skipped_duplicates`
  - `skipped_ambiguous`
  - `skipped_missing_title`
  - per-file decision rows with `file_id`, `original_name`, `title`, `doi`, `decision`, `matched_entry_id`.
- [ ] Run:
  - `python -m unittest backend.tests.test_backfill_uploaded_markdown_library`
  - Expected: pass.

### Task 3: Add Apply Mode

**Files:**
- Modify: `backend/scripts/backfill_uploaded_markdown_library.py`
- Test: `backend/tests/test_backfill_uploaded_markdown_library.py`

- [ ] In `--apply` mode, wrap changes in one transaction.
- [ ] For matched entries:
  - set `markdown_source_file_id` when empty.
  - set `source_file_id` when empty.
  - set `reading_status` from `none` to `has_pdf`.
  - fill empty metadata fields only.
  - update `updated_at`.
- [ ] For new entries:
  - create `BibEntry` with source and Markdown file IDs pointing to the existing `File`.
  - use `source_db="md_extracted"`.
  - set `expires_at` to the source `File.expires_at`.
- [ ] If unique dedup constraint is hit, roll back and print a report row instead of partial success.
- [ ] Run:
  - `python -m unittest backend.tests.test_backfill_uploaded_markdown_library`
  - Expected: pass.

### Task 4: Local Verification

**Files:**
- Verify only.

- [ ] Run:
  - `python -m py_compile backend/scripts/backfill_uploaded_markdown_library.py`
  - `python -m unittest backend.tests.test_backfill_uploaded_markdown_library backend.tests.test_library backend.tests.test_upload`
- [ ] Run:
  - `git diff --check`
- [ ] Expected:
  - all checks pass.

### Task 5: Production Dry Run

**Files:**
- Deploy script only: `backend/scripts/backfill_uploaded_markdown_library.py`

- [ ] Upload the script to `/root/deep-reading-agent/backend/scripts/backfill_uploaded_markdown_library.py`.
- [ ] Run dry-run on the server:

```bash
cd /root/deep-reading-agent/backend
set -a && . ../.env.production && set +a
../venv/bin/python scripts/backfill_uploaded_markdown_library.py \
  --owner-user-id 5 \
  --storage-prefix _uploads/5/ \
  --created-after "2026-06-27T14:39:00" \
  --created-before "2026-06-27T14:42:30" \
  --report-path /tmp/md-library-backfill-user5-dry-run.json \
  --dry-run
```

- [ ] Inspect report:
  - Expected candidate count: `261`.
  - Expected current-user existing matches before first apply: `0`.
  - Expected create count: near `261`, minus duplicate or missing-title skips.
  - No database rows should change.

### Task 6: Backup Then Apply

**Files:**
- Production database only after user confirms dry-run output.

- [ ] Create a narrow backup before writes:

```bash
cd /root/deep-reading-agent
set -a && . .env.production && set +a
pg_dump "$DATABASE_URL" \
  --table=files \
  --table=bib_entries \
  --table=upload_batches \
  --data-only \
  --file=/root/deep-reading-agent/backups/md-library-backfill-user5-20260627.sql
```

- [ ] Apply:

```bash
cd /root/deep-reading-agent/backend
set -a && . ../.env.production && set +a
../venv/bin/python scripts/backfill_uploaded_markdown_library.py \
  --owner-user-id 5 \
  --storage-prefix _uploads/5/ \
  --created-after "2026-06-27T14:39:00" \
  --created-before "2026-06-27T14:42:30" \
  --report-path /tmp/md-library-backfill-user5-apply.json \
  --apply
```

- [ ] Do not restart the service unless code routes are changed. This script only writes database rows.

### Task 7: Post-Apply Verification

**Files:**
- Verify production database and public app.

- [ ] Run database count checks for `owner_user_id=5` only:
  - `files` Markdown candidate count remains `261`.
  - `bib_entries` created or linked count matches apply report.
  - `bib_entries.markdown_source_file_id` points to existing `files.id`.
  - no duplicate `dedup_key` rows exist for owner 5.
- [ ] Open the production app and verify the library page shows the newly created entries.
- [ ] Spot-check 5 entries:
  - title
  - author
  - journal/year
  - DOI
  - Markdown reader opens the linked uploaded file.

## Rollback Plan

If the apply report is wrong:

1. Stop using the affected library entries.
2. Restore from the narrow backup, or run a targeted rollback using the apply report:
   - delete newly created `bib_entries` whose IDs are listed as `created`.
   - clear `markdown_source_file_id` / `source_file_id` changes listed as `linked_existing`.
3. Do not delete files in `_uploads/5`; the source Markdown files are user uploads and should remain intact.

## Self-Review

- The plan covers both possible states: existing owned library matches and empty owned library.
- It does not cross-link across users.
- It does not move or rename source files.
- It is rerunnable because existing entries are matched by DOI/dedup/title before creation.
- It avoids overwriting user-curated metadata.
- It has a dry-run gate and a backup gate before production writes.
