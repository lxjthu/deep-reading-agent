# Research Agent Evidence, Style, And Idea Roadmap

> Updated: 2026-06-20
> Branch: `codex/deepreading-empty-postgres-deploy`
> Related plans:
> - `docs/superpowers/plans/2026-06-12-agent-evidence-ranking-and-writing-style-analysis.md`
> - `docs/superpowers/plans/2026-06-20-econ-management-idea-lab.md`

## Purpose

This roadmap closes the current evidence-ranking slice and sets the next order of work for two related Research Agent capabilities:

1. Original-source writing-style analysis: help users study how an author, journal, or paper writes introductions, theory sections, methods, and argument structures.
2. Economics/management idea lab: help users generate source-backed research questions, mechanisms, hypotheses, evidence gaps, and empirical-design candidates from the local literature library.

The two capabilities should share the same evidence discipline but remain separate tools. Writing-style analysis answers "how is this written?" Idea Lab answers "what can I research from this evidence?"

## Current State

### Completed Locally

Evidence-pack ranking is implemented in `backend/services/research_retrieval.py`:

- `SOURCE_KIND_ORDER` ranks validated original-text evidence ahead of metadata and AI notes within the same source tier.
- P0 evidence remains ahead of P1/P2/P3 evidence.
- `get_evidence_pack()` now returns `source_kind_summary` and `table_summary` so the runtime or UI can explain what kinds of evidence were used.

Regression coverage is implemented in `backend/tests/test_research_retrieval.py`:

- `source_evidence` is asserted to rank before title, abstract, and `reading_item` evidence for a focused entry.
- Evidence-pack summaries are asserted to include source-evidence and table counts.

Validated locally:

```powershell
python -m unittest backend.tests.test_research_retrieval
python -m py_compile backend\services\research_retrieval.py backend\tests\test_research_retrieval.py
```

### Not Yet Done

The writing-style analysis tool is not implemented yet:

- No `backend/services/writing_style_retrieval.py`.
- No `backend/tests/test_writing_style_retrieval.py`.
- No `analyze_writing_style` tool registration.
- No router dispatch for `analyze_writing_style`.
- No runtime intent for `writing_style_analysis`.

The economics/management Idea Lab is still a plan:

- No `backend/services/research_idea_lab.py`.
- No idea-lab tool registration or routing.
- No runtime state summary for idea-lab outputs.

## Roadmap

### Phase 0: Close Evidence Ranking

Goal: make the already-implemented evidence ranking slice stable before adding new tools.

Scope:

- Keep the current `SOURCE_KIND_ORDER` policy.
- Keep `source_kind_summary` and `table_summary`.
- Run targeted tests and compile checks.
- Decide whether to commit this slice before starting the next feature.

Verification:

```powershell
python -m unittest backend.tests.test_research_retrieval
python -m py_compile backend\services\research_retrieval.py backend\tests\test_research_retrieval.py
git diff --check
```

Done when:

- Tests pass locally.
- Diff is limited to evidence ranking and test coverage.
- The slice is committed or explicitly carried forward as known local work.

### Phase 1: Writing-Style Retrieval MVP

Goal: add a read-only tool that retrieves original passages for author, journal, or paper writing-style analysis.

Keep this phase narrow. It should retrieve source passages and instructions for the assistant; it should not call an LLM service, write the database, or run external search.

Files:

- Create `backend/services/writing_style_retrieval.py`.
- Create `backend/tests/test_writing_style_retrieval.py`.
- Modify `backend/services/agent_tool_registry.py`.
- Modify `backend/routers/agent.py`.
- Modify `backend/services/research_agent_runtime.py`.
- Extend `backend/tests/test_agent_tool_registry.py`.
- Extend `backend/tests/test_research_agent_runtime.py`.

Service contract:

- `detect_style_focus(question)` identifies `section_type` as `introduction`, `theory`, `method`, or `general`.
- `extract_style_sections(text, section_type, max_sections)` extracts heading-bounded Markdown sections.
- `select_style_entries(...)` selects candidate `BibEntry` rows by entry ids, author, title, or journal.
- `analyze_writing_style(...)` returns P0 `style_evidence` sections plus analysis instructions.

Tool contract:

- Tool name: `analyze_writing_style`.
- Permission: `read_local`.
- Required argument: `question`.
- Optional arguments: `author_or_journal`, `entry_ids`, `section_type`, `limit_entries`, `max_sections_per_entry`.
- Output must include `style_focus`, `entries`, `style_evidence`, `analysis_instructions`, and `limitations`.

Runtime behavior:

- Requests about writing style, introduction style, theory derivation style, method writing, argumentation style, imitation, or "how to write like this" should prefer `analyze_writing_style`.
- Answers must quote or reference returned `style_evidence`.
- If no original source section is available, the answer should say so and fall back to metadata or notes only when clearly labeled.

Verification:

```powershell
python -m unittest backend.tests.test_writing_style_retrieval backend.tests.test_agent_tool_registry backend.tests.test_research_agent_runtime
python -m py_compile backend\services\writing_style_retrieval.py backend\services\agent_tool_registry.py backend\routers\agent.py backend\services\research_agent_runtime.py
```

Done when:

- The Agent can answer a prompt such as "帮我分析宁健康这篇论文的引言写作风格" by first retrieving local original passages.
- The answer does not invent original text that was not returned by the tool.
- No write operation, external retrieval, or background job is introduced.

### Phase 2: Idea Lab MVP

Goal: add a conservative, source-backed economics/management research-idea workflow on top of the evidence stack.

Do not implement the full June 20 plan in one pass. Start with one read-only tool and keep the internal service functions small.

Files:

- Create `backend/services/research_idea_lab.py`.
- Create `backend/tests/test_research_idea_lab.py`.
- Modify `backend/services/agent_tool_registry.py`.
- Modify `backend/routers/agent.py`.
- Modify `backend/services/research_agent_runtime.py`.
- Extend runtime and registry tests.

Service contract:

- Internal pure functions may produce constructs, gaps, and idea candidates.
- Public tool can initially be only `generate_research_ideas`.
- The tool should internally call `get_evidence_pack()` through the router and then organize results.

Tool contract:

- Tool name: `generate_research_ideas`.
- Permission: `read_local`.
- Required argument: `topic`.
- Optional arguments: `entry_ids`, `keywords`, `max_ideas`.
- Output should include `constructs`, `gaps`, `ideas`, `limitations`, and evidence references.

Runtime behavior:

- Requests about research topics, theory mechanisms, hypotheses, research gaps, variables, identification strategies, and economics/management idea generation should prefer the Idea Lab tool.
- The tool should not claim novelty or causal identification when the local evidence does not support it.
- Missing evidence should be reported as `gap`, `risk`, or `limitation`, not hidden.

Verification:

```powershell
python -m unittest backend.tests.test_research_idea_lab backend.tests.test_agent_tool_registry backend.tests.test_research_agent_runtime backend.tests.test_research_retrieval
python -m py_compile backend\services\research_idea_lab.py backend\services\agent_tool_registry.py backend\routers\agent.py backend\services\research_agent_runtime.py
git diff --check
```

Done when:

- The Agent can answer a prompt such as "基于上一轮这些文献，生成 3 个经济管理研究选题、机制假说和识别策略风险" using local evidence first.
- The response separates evidence-backed claims from speculative ideas.
- No database persistence, UI idea notebook, or external discovery is included in the MVP.

### Phase 3: Shared Evidence UX

Goal: make evidence use visible without adding a large new UI surface.

Scope:

- Surface compact summaries from `source_kind_summary`, `table_summary`, `style_evidence`, and idea-lab outputs in the existing Agent session state panel.
- Avoid new full-page UI unless repeated user testing shows the need.
- Keep cards compact and evidence-oriented.

Possible UI fields:

- Last evidence-pack source summary.
- Last writing-style evidence count.
- Last idea-lab result summary: topic, construct count, gap count, idea count.

Verification:

```powershell
cd frontend
npm run build
```

Done when:

- Users can see whether an answer used original-source snippets, notes, or AI-generated reading items.
- UI changes do not create global CSS leakage or unrelated layout changes.

## Relationship Between The Two Plans

The June 12 plan should be completed first because it strengthens the evidence layer. The June 20 Idea Lab should build on that layer but should not be merged into the writing-style tool.

Shared foundation:

- P0 original text remains the strongest evidence.
- P1 user notes and edits are second.
- P2 AI notes can guide synthesis but cannot override P0/P1.
- Read-only tools return structured evidence; the assistant performs final synthesis.

Separate user jobs:

- `analyze_writing_style`: retrieve and explain how selected papers write.
- `generate_research_ideas`: organize evidence into research questions, mechanisms, hypotheses, gaps, and empirical-design risks.

This separation keeps each tool understandable and avoids turning the Agent runtime into one large multi-purpose branch.

## Deployment Notes

This branch deploys manually. If backend code changes are deployed, follow `docs/MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`.

For Phase 1 or Phase 2 backend-only deployment, expected upload targets are:

- `backend/services/research_retrieval.py`
- `backend/services/writing_style_retrieval.py` or `backend/services/research_idea_lab.py`
- `backend/services/agent_tool_registry.py`
- `backend/routers/agent.py`
- `backend/services/research_agent_runtime.py`

After upload:

```bash
cd /root/deep-reading-agent
/root/deep-reading-agent/venv/bin/python -m py_compile \
  backend/services/research_retrieval.py \
  backend/services/agent_tool_registry.py \
  backend/routers/agent.py \
  backend/services/research_agent_runtime.py
systemctl restart deepreading-api
systemctl is-active deepreading-api
curl -fsS http://127.0.0.1:18000/api/deploy/runtime
```

Do not use the `online` branch webhook for this server-connected branch.
