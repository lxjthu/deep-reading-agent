# Agent Evidence Ranking And Writing Style Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Research Agent evidence ordering so validated original-text snippets are surfaced first, and add an AI assistant workflow for analyzing author/journal writing styles from original source passages.

**Architecture:** Keep retrieval and synthesis separate. Retrieval tools return ranked local evidence with source tiers and original quotes; the AI assistant uses those tool results to synthesize answers, style patterns, and imitation guidance without inventing unsupported examples.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, PostgreSQL FTS/trigram, existing `agent_tool_registry`, `research_retrieval`, `research_agent_runtime`, and local unit tests with SQLite.

---

## Scope

This plan contains two independent but related slices:

1. Evidence-pack ranking: prioritize `reading_source_evidence` when the user asks a focused evidence question about a read paper.
2. Writing-style analysis: add a read-only AI assistant tool that retrieves original passages for requests such as “分析某作者/某期刊论文的引言写作风格/理论推导风格”.

Do not implement write operations, vector search, embeddings, or external retrieval in this slice.

## Files

- Modify `backend/services/research_retrieval.py`: add an explicit evidence ranking policy and optional source-kind summary.
- Modify `backend/tests/test_research_retrieval.py`: cover `reading_source_evidence` ordering ahead of title/abstract/AI notes.
- Create `backend/services/writing_style_retrieval.py`: section detection, entry selection, and source passage extraction for writing-style requests.
- Modify `backend/services/agent_tool_registry.py`: register the new `analyze_writing_style` read tool.
- Modify `backend/routers/agent.py`: route the tool call to `writing_style_retrieval`.
- Modify `backend/services/research_agent_runtime.py`: classify writing-style requests, prefer the style tool, and summarize style evidence in session state.
- Create `backend/tests/test_writing_style_retrieval.py`: pure tests for section detection, ranking, and evidence payload shape.
- Extend `backend/tests/test_agent_tool_registry.py`: schema coverage for the new tool.
- Extend `backend/tests/test_research_agent_runtime.py`: routing policy for style-analysis prompts.
- Optional frontend follow-up: `frontend/src/App.tsx` can surface a compact “writing style evidence” card after backend behavior is stable.

---

### Task 1: Evidence-Pack Ranking Policy

**Files:**
- Modify: `backend/services/research_retrieval.py`
- Test: `backend/tests/test_research_retrieval.py`

- [ ] **Step 1: Write a failing ranking test**

Add a test where one entry has matching `title`, `abstract`, `reading_item`, and `reading_source_evidence`. Assert validated `source_evidence` appears before metadata and AI notes.

```python
def test_source_evidence_ranks_ahead_of_metadata_for_focused_entry(self) -> None:
    ids = self.seed_library()

    async def run():
        async with AsyncSessionLocal() as session:
            return await get_evidence_pack(
                session,
                owner_user_id=ids["owner_id"],
                query=ResearchQuery(
                    question="platform responsibility core governance obligation",
                    entry_ids=[ids["entry_id"]],
                    limit_evidence_per_entry=8,
                ),
            )

    pack = asyncio.run(run())
    evidence = pack["entries"][0]["evidence"]
    source_idx = next(i for i, ev in enumerate(evidence) if ev["source_kind"] == "source_evidence")
    abstract_idx = next(i for i, ev in enumerate(evidence) if ev["source_kind"] == "abstract")
    reading_idx = next(i for i, ev in enumerate(evidence) if ev["source_kind"] == "reading_item")
    self.assertLess(source_idx, abstract_idx)
    self.assertLess(source_idx, reading_idx)
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
python -m unittest backend.tests.test_research_retrieval.ResearchRetrievalTests.test_source_evidence_ranks_ahead_of_metadata_for_focused_entry
```

Expected before implementation: failure because current ordering still allows metadata P0 to compete with source evidence by score.

- [ ] **Step 3: Add explicit source-kind priority**

In `backend/services/research_retrieval.py`, replace `_sort_evidence` with a policy that sorts by tier first, then source-kind priority, then score.

```python
SOURCE_KIND_ORDER = {
    "source_evidence": 0,
    "source_window": 1,
    "citation": 2,
    "reference": 3,
    "doi": 4,
    "title": 5,
    "abstract": 6,
    "user_note": 7,
    "edited_reading_item": 8,
    "annotation": 9,
    "card_note": 10,
    "reading_item": 11,
}


def _sort_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            TIER_ORDER.get(str(item.get("source_tier")), 99),
            SOURCE_KIND_ORDER.get(str(item.get("source_kind") or ""), 99),
            -float(item.get("score") or 0),
            str(item.get("item_label") or ""),
        ),
    )
```

This keeps P0 before P1/P2, but among P0 evidence it prefers validated source snippets over title/abstract matches.

- [ ] **Step 4: Preserve source-evidence discovery**

Confirm `_load_entries()` still includes `reading_source_evidence` matches when the entry was not already found by `bib_entries`.

Run:

```powershell
python -m unittest backend.tests.test_research_retrieval
```

Expected: all tests pass.

- [ ] **Step 5: Add a source-kind summary to evidence packs**

Extend `get_evidence_pack()` to return optional aggregate counts:

```python
source_kind_summary: dict[str, int] = {}
table_summary: dict[str, int] = {}
for entry in results:
    for evidence in entry.get("evidence") or []:
        kind = str(evidence.get("source_kind") or "")
        table = str(evidence.get("table") or "")
        if kind:
            source_kind_summary[kind] = source_kind_summary.get(kind, 0) + 1
        if table:
            table_summary[table] = table_summary.get(table, 0) + 1
return {
    "question": query.question,
    "entries": results,
    "source_kind_summary": source_kind_summary,
    "table_summary": table_summary,
    "external_evidence": [],
    "limitations": ["未联网检索；如需最新外部证据，需要先获得用户明确授权。"],
}
```

This gives the runtime/UI a clean way to say “this answer used 20 original-source snippets”.

---

### Task 2: Writing-Style Retrieval Service

**Files:**
- Create: `backend/services/writing_style_retrieval.py`
- Test: `backend/tests/test_writing_style_retrieval.py`

- [ ] **Step 1: Write pure tests for style intent parsing**

Create `backend/tests/test_writing_style_retrieval.py`.

```python
from backend.services.writing_style_retrieval import detect_style_focus


def test_detect_introduction_style_focus() -> None:
    focus = detect_style_focus("帮我分析宁健康这篇论文的引言写作风格")
    assert focus["section_type"] == "introduction"
    assert focus["style_type"] == "writing"


def test_detect_theory_derivation_style_focus() -> None:
    focus = detect_style_focus("分析中国农村经济论文的理论推导风格")
    assert focus["section_type"] == "theory"
    assert focus["style_type"] == "theory_derivation"
```

- [ ] **Step 2: Implement minimal focus detection**

```python
def detect_style_focus(question: str) -> dict[str, str]:
    text = question or ""
    if any(token in text for token in ("引言", "导论", "Introduction")):
        section_type = "introduction"
    elif any(token in text for token in ("理论推导", "理论机制", "理论框架")):
        section_type = "theory"
    elif any(token in text for token in ("方法", "模型", "实证设计")):
        section_type = "method"
    else:
        section_type = "general"

    style_type = "theory_derivation" if section_type == "theory" else "writing"
    return {"section_type": section_type, "style_type": style_type}
```

- [ ] **Step 3: Write section extraction tests**

Use a small Markdown-like source string.

```python
from backend.services.writing_style_retrieval import extract_style_sections


def test_extract_introduction_section() -> None:
    text = "# 标题\n\n## 引言\n\n第一段提出问题。\n\n第二段建立研究缺口。\n\n## 理论分析\n\n理论段。"
    sections = extract_style_sections(text, section_type="introduction", max_sections=3)
    assert len(sections) == 1
    assert sections[0]["heading"] == "引言"
    assert "研究缺口" in sections[0]["text"]
```

- [ ] **Step 4: Implement heading-based extraction**

Implement `extract_style_sections(text, section_type, max_sections=5)` with these heading patterns:

```python
SECTION_HEADING_PATTERNS = {
    "introduction": [r"引言", r"导论", r"绪论", r"Introduction"],
    "theory": [r"理论", r"机制", r"理论分析", r"理论框架", r"研究假说"],
    "method": [r"方法", r"模型", r"研究设计", r"数据", r"变量"],
    "general": [r"引言", r"理论", r"方法", r"结论"],
}
```

Return section dictionaries:

```python
{
    "heading": heading,
    "section_type": section_type,
    "text": section_text[:6000],
    "char_start": start,
    "char_end": end,
}
```

- [ ] **Step 5: Add entry selection tests**

Seed entries with authors and journal. Test author and journal filters.

```python
def test_select_entries_by_author_and_journal(self) -> None:
    async def run():
        async with AsyncSessionLocal() as db:
            return await select_style_entries(
                db,
                owner_user_id=1,
                author_or_journal="宁健康",
                limit_entries=5,
            )
    entries = asyncio.run(run())
    self.assertEqual(entries[0].title, "我国农业新质生产力：统计测度与时空演进")
```

- [ ] **Step 6: Implement `select_style_entries()`**

Use existing `BibEntry` fields only:

```python
stmt = select(BibEntry).where(BibEntry.owner_user_id == owner_user_id)
if author_or_journal:
    like = f"%{author_or_journal}%"
    stmt = stmt.where(
        or_(
            BibEntry.title.ilike(like),
            BibEntry.authors_json.ilike(like),
            BibEntry.journal.ilike(like),
        )
    )
stmt = stmt.order_by(BibEntry.updated_at.desc()).limit(limit_entries)
```

- [ ] **Step 7: Implement source text loading**

For each selected entry:

1. Prefer `markdown_source_file_id`.
2. Else use `source_file_id`.
3. Resolve file through `upload_storage.resolve_storage_path`.
4. For Markdown, read text directly.
5. For PDF, use existing `routers.reading.extract_paper_text` only in the backend worker context.

Return a source issue instead of failing the whole tool when a file cannot be read.

- [ ] **Step 8: Implement `analyze_writing_style()` retrieval payload**

The service function should be read-only and return:

```python
{
    "question": question,
    "style_focus": {"section_type": "introduction", "style_type": "writing"},
    "entries": [
        {
            "entry_id": entry.id,
            "title": entry.title,
            "authors": authors,
            "journal": entry.journal,
            "style_evidence": [
                {
                    "source_tier": "P0",
                    "source_kind": "style_source_section",
                    "table": "files",
                    "heading": "引言",
                    "char_start": 120,
                    "char_end": 1800,
                    "quote": "...",
                }
            ],
        }
    ],
    "analysis_instructions": [
        "从问题提出方式、研究缺口铺垫、概念推进、句式节奏、引用组织、转折与收束方式分析写作风格。",
        "必须引用 style_evidence 中的原文片段，不得编造原文。",
        "最后输出可模仿的写作模板和注意事项。"
    ],
    "limitations": [],
}
```

The tool must not call DeepSeek itself.

---

### Task 3: Register AI Assistant Tool

**Files:**
- Modify: `backend/services/agent_tool_registry.py`
- Modify: `backend/routers/agent.py`
- Test: `backend/tests/test_agent_tool_registry.py`

- [ ] **Step 1: Add schema test**

```python
def test_analyze_writing_style_tool_is_registered_as_read_only(self) -> None:
    tool = registry.get("analyze_writing_style")
    self.assertEqual(tool.handler, "analyze_writing_style")
    self.assertEqual(tool.capability, "local_read")
    self.assertIn("question", tool.parameters["required"])
```

- [ ] **Step 2: Register tool**

Add a `ToolSpec`:

```python
ToolSpec(
    name="analyze_writing_style",
    description=(
        "Retrieve original-source passages for author, journal, or paper writing-style analysis. "
        "Use for prompts about introduction style, theory derivation style, method-writing style, "
        "argumentation style, or imitation learning from original academic prose."
    ),
    capability="local_read",
    handler="analyze_writing_style",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "author_or_journal": {"type": "string"},
            "entry_ids": {"type": "array", "items": {"type": "string"}},
            "section_type": {
                "type": "string",
                "enum": ["", "introduction", "theory", "method", "general"],
            },
            "limit_entries": {"type": "integer", "minimum": 1, "maximum": 20},
            "max_sections_per_entry": {"type": "integer", "minimum": 1, "maximum": 8},
        },
        "required": ["question"],
    },
)
```

- [ ] **Step 3: Route tool execution**

In `backend/routers/agent.py`, add:

```python
if name == "analyze_writing_style":
    from backend.services.writing_style_retrieval import analyze_writing_style
    return await analyze_writing_style(
        db,
        owner_user_id=user.id,
        question=str(args.get("question") or ""),
        author_or_journal=str(args.get("author_or_journal") or ""),
        entry_ids=[str(item) for item in args.get("entry_ids") or []],
        section_type=str(args.get("section_type") or ""),
        limit_entries=max(1, min(int(args.get("limit_entries") or 5), 20)),
        max_sections_per_entry=max(1, min(int(args.get("max_sections_per_entry") or 3), 8)),
    )
```

---

### Task 4: Runtime Policy For Style Requests

**Files:**
- Modify: `backend/services/research_agent_runtime.py`
- Test: `backend/tests/test_research_agent_runtime.py`

- [ ] **Step 1: Add intent test**

```python
def test_style_request_prefers_writing_style_tool() -> None:
    frame = build_task_frame("帮我分析宁健康这篇论文的引言写作风格")
    assert frame["intent"] == "writing_style_analysis"
```

- [ ] **Step 2: Add preferred tool test**

```python
def test_style_request_recommends_analyze_writing_style() -> None:
    tools = preferred_tools_for_intent({"intent": "writing_style_analysis"})
    assert tools[0] == "analyze_writing_style"
```

- [ ] **Step 3: Implement runtime classification**

Add writing-style keywords:

```python
STYLE_REQUEST_KEYWORDS = (
    "写作风格",
    "引言风格",
    "理论推导风格",
    "行文风格",
    "论证风格",
    "模仿",
    "仿写",
    "怎么写",
)
```

When the message includes one of these keywords and mentions “作者/期刊/论文/引言/理论/方法”, set:

```python
task_frame["intent"] = "writing_style_analysis"
task_frame["requires_local_search"] = True
task_frame["requires_external_search"] = False
```

- [ ] **Step 4: Add system instruction**

In the AI assistant system prompt, add:

```text
当用户询问某作者、某期刊或某篇论文的引言写作风格、理论推导风格、方法写法、论证风格或仿写学习时，优先调用 analyze_writing_style。回答必须基于工具返回的原文片段，总结可模仿的结构、句式、论证节奏和禁忌；不得编造未返回的原文。
```

---

### Task 5: Verification And Deploy

**Files:**
- No new files beyond Tasks 1-4.

- [ ] **Step 1: Run backend tests**

```powershell
python -m unittest backend.tests.test_research_retrieval backend.tests.test_writing_style_retrieval backend.tests.test_agent_tool_registry backend.tests.test_research_agent_runtime
```

Expected: all tests pass.

- [ ] **Step 2: Compile changed Python files**

```powershell
python -m py_compile backend\services\research_retrieval.py backend\services\writing_style_retrieval.py backend\services\agent_tool_registry.py backend\routers\agent.py backend\services\research_agent_runtime.py
```

Expected: no output.

- [ ] **Step 3: Manual deploy**

Follow `docs/MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`.

Upload backend files:

```powershell
scp backend\services\research_retrieval.py root@8.162.14.154:/root/deep-reading-agent/backend/services/research_retrieval.py
scp backend\services\writing_style_retrieval.py root@8.162.14.154:/root/deep-reading-agent/backend/services/writing_style_retrieval.py
scp backend\services\agent_tool_registry.py root@8.162.14.154:/root/deep-reading-agent/backend/services/agent_tool_registry.py
scp backend\routers\agent.py root@8.162.14.154:/root/deep-reading-agent/backend/routers/agent.py
scp backend\services\research_agent_runtime.py root@8.162.14.154:/root/deep-reading-agent/backend/services/research_agent_runtime.py
```

Server-side verification:

```bash
cd /root/deep-reading-agent
/root/deep-reading-agent/venv/bin/python -m py_compile \
  backend/services/research_retrieval.py \
  backend/services/writing_style_retrieval.py \
  backend/services/agent_tool_registry.py \
  backend/routers/agent.py \
  backend/services/research_agent_runtime.py
systemctl restart deepreading-api
systemctl is-active deepreading-api
curl -fsS http://127.0.0.1:18000/api/deploy/runtime
```

Expected: service is `active`, runtime endpoint returns JSON.

---

## Self-Review

- Spec coverage: evidence-pack ranking is Task 1; writing-style source retrieval is Task 2; AI assistant tool exposure is Task 3; runtime routing is Task 4; verification/deploy is Task 5.
- Placeholder scan: no task uses TBD/TODO/fill-in language.
- Type consistency: `analyze_writing_style`, `section_type`, `style_evidence`, and `source_kind="style_source_section"` are used consistently across tasks.
