# Writing Style Analysis Workflow Design

> Date: 2026-06-21
> Scope: First version of a source-backed writing-style analysis workflow for the Deep Reading Agent literature library.

## 1. Goal

Add a dedicated "writing style analysis" workflow for papers in "我的文献库".

The workflow should help users:

- Analyze the writing style of each major part of one paper.
- Compare writing styles across multiple papers.
- Summarize shared style patterns and distinctive traits.
- Produce practical imitation and writing advice.
- Save the result to history as a reusable Markdown artifact.

The first version is intentionally narrow: it only analyzes papers that already have a bound Markdown original source. It does not use abstracts, AI reading notes, translated text, or external search as substitutes for original prose.

## 2. First-Version Boundary

### Included

- A "风格分析" action in "我的文献库" for one selected paper or multiple selected papers.
- Backend reading of bound Markdown original sources.
- Original-source section extraction for common paper sections:
  - title / abstract if present in Markdown
  - introduction
  - literature review / theory / hypothesis
  - data / method / identification
  - results / discussion
  - conclusion
- Model-generated Markdown report based on extracted source sections.
- Prompt slots stored in the existing prompt management system.
- Saved history artifact for successful reports.
- Clear feedback for papers that cannot be analyzed because Markdown original source is missing.

### Excluded

- No fallback to abstract-only analysis.
- No fallback to AI reading notes.
- No automatic external search.
- No automatic PaddleOCR job.
- No automatic PDF-to-Markdown conversion in this workflow.
- No new notebook or long-term style library in the first version.

The user-facing rule is simple: original writing-style analysis requires original Markdown text.

## 3. Missing Markdown Behavior

If a selected paper has no bound Markdown original source, the system must not silently fall back to weaker evidence.

For one selected paper:

- Do not start the analysis.
- Show a clear message:

```text
这篇论文暂时无法进行原文写作风格分析。请先使用 PaddleOCR 将 PDF 转换为 Markdown，并把 Markdown 原文挂载/绑定到这篇文献后再分析。
```

For multiple selected papers:

- Analyze only papers with bound Markdown original sources.
- Put skipped papers in a "未分析论文" section in the final report.
- For each skipped paper, explain that it needs PaddleOCR conversion to Markdown and binding before style analysis.
- If none of the selected papers has Markdown, do not create a history artifact.

## 4. Prompt Management

Add a new prompt type:

```text
writing_style
```

Add it to `PROMPT_TYPE_LABELS` as:

```text
写作风格分析
```

Recommended prompt slots:

1. `section_analyzer`
   - Purpose: analyze writing style by paper section.
   - Input: paper metadata, section name, original source excerpts.
   - Output: style observations grounded in quoted or referenced excerpts.

2. `imitation_advisor`
   - Purpose: generate imitation advice.
   - Input: section-level style observations.
   - Output: reusable structures, sentence patterns, argument rhythm, transition tactics, and pitfalls.

3. `comparative_synthesizer`
   - Purpose: compare multiple papers.
   - Input: per-paper style observations.
   - Output: common patterns, distinctive differences, and when to imitate each style.

4. `report_writer`
   - Purpose: assemble final Markdown report.
   - Input: metadata, evidence summary, style observations, imitation advice, skipped papers.
   - Output: polished Markdown saved to history.

Default prompt files should live under:

```text
prompts/writing_style/
  section_analyzer.md
  imitation_advisor.md
  comparative_synthesizer.md
  report_writer.md
```

The workflow should use `prompt_service.get_effective_prompt_text()` so user overrides in the prompt management module take effect.

## 5. Backend Design

### New service

Create:

```text
backend/services/writing_style_analysis.py
```

Responsibilities:

- Validate selected entry ids belong to the current user.
- Load bound Markdown source files.
- Split Markdown into section groups.
- Call the model using managed prompts.
- Generate a final Markdown report.
- Return skipped-paper reasons.

The service should reuse logic from `backend/services/writing_style_retrieval.py` where possible, especially:

- source ownership checks
- Markdown path resolution
- section extraction helpers
- limitations wording

### API route

Add a route in the library or a dedicated writing-style router. A focused route is preferable if the implementation grows:

```text
POST /api/library/writing-style/analyze
```

Request:

```json
{
  "entry_ids": ["..."],
  "api_key": "...",
  "analysis_mode": "auto"
}
```

First version can keep `analysis_mode` simple:

- one paper: single-paper report
- multiple papers: comparative report

Response:

```json
{
  "job_id": "...",
  "artifact_id": 123,
  "filename": "...",
  "analyzed_count": 2,
  "skipped": [
    {
      "entry_id": "...",
      "title": "...",
      "reason": "missing_markdown_source",
      "message": "请先使用 PaddleOCR 将 PDF 转换为 Markdown，并把 Markdown 原文挂载/绑定到这篇文献后再分析。"
    }
  ]
}
```

For the first version, this can be synchronous if typical selected paper counts are small. If model latency becomes a problem, move to a normal `Job` status flow later.

### Artifact and history

Add a new artifact type:

```text
writing_style_md
```

This requires a database migration because `Artifact.artifact_type` has a CHECK constraint.

The artifact should be saved under the current history/output convention, with a Markdown filename such as:

```text
writing_style_YYYYMMDD_HHMMSS.md
```

The history page should label it:

```text
写作风格分析
```

### Job type

Add a job type:

```text
writing_style
```

This also requires a migration because `Job.job_type` has a CHECK constraint.

The job gives the artifact a normal lifecycle and makes the result consistent with history and other generated outputs.

## 6. Database and Portability

Because this adds `Job.job_type` and `Artifact.artifact_type` values, update:

- `backend/db/models.py`
- Alembic migration under `backend/migrations/versions/`
- `docs/DATABASE_SCHEMA.md`
- `backend/services/data_portability.py`

For `.dra` export/import:

- Include `writing_style_md` artifacts in the normal artifact export/import flow if artifacts are already exported generically.
- Confirm any job type filtering or artifact type filtering does not drop the new output.
- If no special handling is required, add a short code comment or test expectation showing the generic artifact path covers it.

## 7. Frontend Design

### Library action

In `frontend/src/LibraryTab.tsx`, add a "风格分析" action:

- Single paper card action.
- Multi-select batch action if selection mode is available.

Button behavior:

- If all selected papers lack Markdown source, show a blocking message with PaddleOCR guidance.
- If some selected papers have Markdown, allow analysis and warn that missing ones will be skipped.
- Disable the button while analysis is running.

### User feedback

Show progress states:

- `准备原文`
- `分析写作风格`
- `生成报告`
- `保存到历史记录`

On success:

```text
写作风格分析已保存到历史记录：{filename}
```

On missing Markdown:

```text
未分析的论文需要先使用 PaddleOCR 将 PDF 转换为 Markdown，并把 Markdown 原文挂载/绑定到对应文献。
```

### History

In history display:

- Show `writing_style_md` as "写作风格分析".
- Support preview and download through existing history preview endpoints.

## 8. Report Structure

The saved Markdown report should use this structure:

```markdown
---
type: writing_style_analysis
generated_at: ...
entry_count: ...
source_requirement: markdown_original_only
---

# 写作风格分析报告

## 分析范围

## 原文证据概览

## 单篇论文写作风格

### 论文 A

#### 引言写法
#### 理论与文献写法
#### 方法与识别写法
#### 结果与讨论写法
#### 结论写法
#### 可模仿建议

## 多篇论文对比

## 共性模式

## 差异特点

## 写作建议

## 未分析论文
```

For one paper, omit or simplify the multi-paper comparison sections.

Every analytical claim about style should be grounded in returned Markdown source excerpts. The report may paraphrase, but it must not invent original wording.

## 9. Error Handling

Important cases:

- No selected entries: return 400.
- Selected entries not owned by current user: ignore or return 404, following existing library behavior.
- No Markdown source for any selected entry: return a structured error, do not create job/artifact.
- Some Markdown files missing on disk: skip those papers and list them in the report.
- Model timeout: mark job failed and return a user-facing retry message.
- Invalid API key: reuse existing API key validation behavior.

## 10. Testing Plan

Backend tests:

- Prompt registry exposes `writing_style` slots.
- Missing Markdown returns PaddleOCR guidance and creates no artifact.
- One Markdown-backed paper creates `writing_style_md`.
- Multiple papers create a comparative report and list skipped papers.
- Artifact appears in history list with the right label.
- Data portability does not drop `writing_style_md`.

Frontend tests or manual checks:

- Button appears in library actions.
- Missing Markdown warning is visible.
- Partial skip warning is visible.
- Successful report shows "saved to history".
- History preview opens the generated Markdown.

Deployment checks:

```powershell
python -m unittest backend.tests.test_writing_style_analysis backend.tests.test_prompt_service backend.tests.test_history
python -m py_compile backend\services\writing_style_analysis.py backend\routers\library.py backend\routers\history.py backend\prompt_registry.py
cd frontend
npm run build
```

If migrations are added:

```powershell
cd backend
python -m alembic upgrade head
```

On the production branch, deploy manually using `docs/MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`.

## 11. Implementation Order

1. Add prompt registry slots and default prompt files.
2. Add migration for `writing_style` job type and `writing_style_md` artifact type.
3. Add backend service for Markdown-only style analysis.
4. Add API route.
5. Add history label and preview support.
6. Add frontend "风格分析" button and status feedback.
7. Add tests and run local validation.
8. Deploy manually and verify with one Markdown-backed paper and one missing-Markdown paper.

## 12. Open Decisions

For the first implementation pass, choose these defaults:

- Maximum selected papers: 5.
- Maximum sections per paper: 8.
- Maximum source excerpt characters per section: 1800.
- First version is synchronous unless local testing shows request timeouts.

These limits can be adjusted after the first manual test.
