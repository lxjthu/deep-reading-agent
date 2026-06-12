# Research Agent Runtime Roadmap 2026-06-02

> Status: active roadmap; Phase 1 and Phase 1.5 are implemented, deployed, and user-verified on 2026-06-03.
> Scope: current `codex/deepreading-empty-postgres-deploy` branch and the production-connected AI assistant at `http://8.162.14.154:18080/`.
> Related docs: `RESEARCH_AGENT_UPGRADE_PLAN.md`, `RESEARCH_AGENT_IMPLEMENTATION_ROADMAP_2026_05_31.md`, `RESEARCH_AGENT_IMPLEMENTATION.md`.

## 1. Goal

Turn the current AI assistant from "LLM tool calling with runtime guardrails" into a small, testable, runtime-driven research agent.

The next implementation work should not add more loose tools first. It should make the assistant decide, in code, whether it understands the task, what evidence it has, whether that evidence is enough, whether it needs user consent, and which proposal is safe to prepare.

## 2. Current Baseline

Already implemented:

- Persistent agent sessions, messages, action proposals, and `last_state_json`.
- Tool registry with local read tools, proposal-only write tools, and external read tools.
- P0/P1/P2/P3 evidence retrieval with local-first behavior.
- Basic TaskFrame, context resolver, result set state, analysis cache, tool trace, budget snapshot, and runtime notices.
- Frontend AI assistant panel with sessions, proposal confirmation, runtime notices, analysis cache summary, and tool trace display.
- Pure sufficiency engine for `get_evidence_pack` results, persisted as `last_sufficiency` and surfaced in the AI assistant sidebar.
- Explicit scan continuation metadata through `scan_plan`, including offsets, remaining count, and frontend batch workflow display.

Still incomplete:

- No explicit state machine. `agent_chat` still loops over LLM tool calls directly.
- Sufficiency is not yet enforced as a required runtime transition; natural evidence questions can still route through `research_search` without producing `last_sufficiency`.
- Focused evidence packs can already include `reading_source_evidence`, but the internal ordering still needs an explicit policy so validated original-text snippets appear ahead of title/abstract or AI-note matches.
- No durable external consent ticket.
- Result sets are useful but not complete enough for named sets and stable follow-up references.
- Compare, synthesis, translation, references, cards, and annotations are not fully covered as runtime tools.
- Writing-style questions such as "analyze this author's introduction style" or "analyze this journal's theory-derivation style" do not yet have a dedicated original-passage retrieval tool.
- Agent tests now cover the Phase 1/1.5 pure modules and narrow runtime wiring, but the Phase 2 state machine still needs its own test suite.

## 3. Product Rules

These rules are not optional:

1. Local evidence first. External retrieval is allowed only after explicit user intent or consent.
2. P0/P1 evidence outranks P2 AI notes. P3 external results are temporary unless the user explicitly saves them.
3. Write operations must create proposals and execute only after user confirmation.
4. Runtime decisions must be testable without calling the LLM.
5. The UI should explain what evidence was used, why the agent stopped, and what needs user action.

## 4. Implementation Phases

### Phase 1: Sufficiency Engine and Test Baseline

Goal: extract evidence adequacy into a pure, tested module that later becomes a state-machine transition.

Files:

- Create `backend/services/research_sufficiency.py`.
- Create `backend/tests/test_research_sufficiency.py`.
- Modify `backend/services/research_agent_runtime.py`.

Behavior:

- Given an evidence pack, count P0/P1/P2/P3 evidence.
- Mark evidence sufficient when at least one P0 or P1 item exists.
- Mark P2-only evidence as usable with warning, not authoritative.
- Request external consent only when evidence is empty or P2-only and the user asked for external lookup.
- Store the sufficiency summary in session state after `get_evidence_pack`.

Verification:

```powershell
python -m unittest backend.tests.test_research_sufficiency
python -m py_compile backend\services\research_sufficiency.py backend\services\research_agent_runtime.py
```

### Phase 1.5: Iterative Full-Batch Scan Loop

Goal: make every batch scan path explicit about full-corpus traversal instead of silently stopping at the first returned batch.

Files:

- Modify `backend/routers/agent.py`.
- Modify `backend/services/agent_tool_registry.py`.
- Modify `backend/services/research_agent_runtime.py`.
- Modify `frontend/src/App.tsx`.
- Extend `backend/tests/test_agent_inbox_observability.py`.
- Extend `backend/tests/test_agent_tool_registry.py`.

Behavior:

- `scan_input_folder` returns a `scan_plan` with `offset`, `batch_size`, `processed_total`, `total_available`, `remaining_count`, `has_next_batch`, and `next_offset`.
- When `has_next_batch=true`, the agent treats the current result as an intermediate batch: settle a short working note, call `scan_input_folder` again with `offset=next_offset`, iterate the notes, and only then produce the final complete result.
- Tool schemas expose `offset` and raise the safe per-call scan cap to 500, so a 200-paper upload is no longer hidden behind a 100-paper schema cap.
- The frontend scan summary displays batch traversal state and the expected workflow steps.

Verification:

```powershell
python -m unittest backend.tests.test_agent_tool_registry backend.tests.test_agent_inbox_observability backend.tests.test_research_agent_runtime
python -m py_compile backend\routers\agent.py backend\services\agent_tool_registry.py backend\services\research_agent_runtime.py
cd frontend && npm run build
```

### Phase 2: Explicit Runtime State Machine

Goal: replace the free tool-call loop with a small state transition layer.

Files:

- Modify `backend/services/research_agent_runtime.py`.
- Modify `backend/routers/agent.py`.
- Add `backend/tests/test_research_agent_runtime_state.py`.

States:

- `understand`
- `resolve_context`
- `retrieve_local`
- `assess_sufficiency`
- `request_external_consent`
- `retrieve_external`
- `synthesize_answer`
- `prepare_proposal`
- `finish`

Acceptance:

- Each turn records the current state and last transition reason.
- Evidence questions pass through `assess_sufficiency`.
- The router owns SSE and persistence; the runtime owns decisions.

### Phase 3: Consent Tickets and External Evidence

Goal: make external lookup a first-class user-authorized flow.

Files:

- Create `backend/services/external_retrieval_policy.py`.
- Modify `backend/services/agent_tool_registry.py`.
- Modify `backend/routers/agent.py`.
- Modify `frontend/src/App.tsx`.

Behavior:

- Add a consent ticket object to session state.
- External tools require a matching ticket unless the current user message explicitly asked for that external action.
- External results are tagged P3 and remain temporary.
- Frontend displays why internet access is requested and what will be opened.

### Phase 4: Result Sets and Evidence UI

Goal: make follow-up work reliable and explainable.

Files:

- Modify `backend/services/research_agent_runtime.py`.
- Modify `frontend/src/App.tsx`.

Behavior:

- Add `scope_label`, `titles`, `created_at`, and `expires_at` to result sets.
- Support named result sets in session state.
- Add UI cards for result sets and evidence tier summaries.

### Phase 5: Tool Coverage Expansion

Goal: connect common research workflows to the runtime after the runtime is stable.

Tool families:

- Compare and synthesis read/proposal tools.
- Translation read/proposal tools.
- References and citation evidence read tools.
- Cards and annotations read/proposal tools.
- Dimension-set read tools.
- Writing-style analysis read tool: retrieve original introduction/theory/method passages by author, journal, or selected paper, then let the assistant synthesize reusable style patterns and imitation guidance from those passages.

Acceptance:

- New tools use the registry.
- Write tools are proposal-only.
- Each tool family has at least one pure policy or adapter test.

## 5. Implemented Slices

Phase 1:

1. Add `research_sufficiency.py`.
2. Add focused unit tests.
3. Wire `get_evidence_pack` results into `last_sufficiency` in session state.
4. Surface that state through `summarize_state_for_ui`.

Phase 1.5:

1. Add explicit scan continuation state through `scan_plan`.
2. Add `offset` to scan tools and remove the hidden 100-item schema ceiling.
3. Surface full-batch traversal state in the AI assistant sidebar.
4. Keep actual note synthesis on the existing `working_notes` / `analyze_reading_candidates` path, while making scan batches declare when the agent must continue before finalizing.

These slices are intentionally small. They give the next state-machine work tested decision objects without disturbing the production chat loop yet.

## 5.5 Planned Follow-Up Slices

2026-06-12:

- Evidence-pack ranking: keep the existing P0/P1/P2/P3 rule, but within the same tier rank validated `reading_source_evidence` before title, abstract, and AI reading-note matches. This is especially important after a paper has been deeply read, because focused follow-up questions should see original source snippets first.
- Evidence-pack observability: add `source_kind_summary` and `table_summary` to `get_evidence_pack` results so the runtime and UI can explain how many items came from original-text evidence, metadata, notes, references, or other sources.
- Writing-style analysis: add a read-only AI assistant tool, tentatively `analyze_writing_style`, for requests such as "analyze XX author's introduction writing style" or "analyze XX journal papers' theory-derivation style." The tool should extract relevant original sections from local source text, return concise original-passage evidence, and leave the final synthesis to the assistant.
- Scope guardrails: this slice should not add embeddings, vector storage, online retrieval, or write operations. It should reuse local PostgreSQL search, existing source files, and the newly stored source evidence where useful.

Acceptance:

- For a focused read-paper evidence question, P0 `source_evidence` appears before P0 metadata and P2 AI notes in the returned evidence pack.
- For a writing-style request, the assistant calls the style retrieval tool and cites returned original passages before distilling style patterns.
- If original sections cannot be found locally, the tool returns a clear limitation instead of inventing examples.

Detailed plan: `docs/superpowers/plans/2026-06-12-agent-evidence-ranking-and-writing-style-analysis.md`.

## 6. Deployment and Verification Notes

2026-06-03:

- Local verification passed:

```powershell
python -m unittest backend.tests.test_research_sufficiency backend.tests.test_agent_tool_registry backend.tests.test_agent_inbox_observability backend.tests.test_research_agent_runtime
python -m py_compile backend\services\research_sufficiency.py backend\services\research_agent_runtime.py backend\routers\agent.py backend\services\agent_tool_registry.py
cd frontend && npm run build
```

- Production deployment followed `docs/MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`: upload the scoped backend files and `frontend/dist`, run server-side `py_compile`, restart `deepreading-api` through `systemctl`, then verify `/` and `/api/deploy/runtime` both return `200`.
- User verification passed for the intended Phase 1/1.5 behavior:
  - `get_evidence_pack`-based follow-up writes `last_sufficiency` and displays the evidence status card.
  - The 200-file uploaded batch records `scan_plan` with `processed_total=200`, `total_available=200`, `has_next_batch=false`, and the frontend shows the batch workflow state.
- Known boundary kept for the next slice: evidence-rich `research_search` results can include P0/P2 evidence but still do not write `last_sufficiency`. The smallest next fix is to route `research_search` evidence through `assess_evidence_sufficiency()` or make Phase 2 require an `assess_sufficiency` transition for evidence questions.
