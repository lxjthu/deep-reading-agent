# Economic Management Idea Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an economics/management-oriented research idea lab that extracts theoretical constructs, mechanisms, empirical designs, evidence gaps, and research idea candidates from the user's local literature library.

**Architecture:** Reuse the existing `deep-reading-agent` evidence stack instead of importing AI-Researcher directly. Add a small structured analysis layer over `research_search`, `get_evidence_pack`, `get_source_windows`, and `analysis_cache`, then expose read-only tools that can be used by the existing research agent runtime. The first version produces structured notes and idea candidates only; it does not launch reading jobs, write papers, run code, or use Docker.

**Tech Stack:** Python 3, FastAPI backend services, SQLAlchemy models already present in the app, OpenAI-compatible tool schemas, `unittest`, existing research runtime state objects.

---

## Scope And Non-Goals

This plan adapts useful ideas from AI-Researcher:

- Atomic concept decomposition.
- Paper-survey style evidence extraction.
- Structured notes that bridge theory, evidence, and research design.
- Stage outputs that can be reused across turns.

This plan does not migrate:

- Docker execution.
- ML code implementation agents.
- GitHub repository selection.
- ChromaDB memory.
- Paper-writing automation.

The target domain is economics and management research. The language of the feature should be about theory, mechanisms, variables, identification, data, institutional context, and contribution, not "model implementation" or "training/testing".

## Existing System Fit

The current app already has stronger foundations than AI-Researcher for this product:

- `backend/services/research_retrieval.py`
  - `research_search`
  - `get_evidence_pack`
  - `get_source_windows`
  - P0/P1/P2 evidence tiers
- `backend/services/research_agent_runtime.py`
  - task frames
  - result-set continuation
  - analysis cache
  - tool policy
  - external consent gate
- `backend/services/agent_tool_registry.py`
  - OpenAI-compatible tool schemas
  - permission metadata
- `backend/services/reading_candidate_analysis.py`
  - batch analysis and `analysis_cache`

The new feature should be read-local by default. It should only use external tools if the user explicitly requests external search.

## Proposed Files

- Create: `backend/services/research_idea_lab.py`
  - Owns structured dataclasses and pure functions for construct extraction, gap diagnosis, and idea candidate generation.
  - Does not call LLM providers directly in the first version.
  - Consumes evidence packs, source windows, and cached analysis entries.

- Modify: `backend/services/agent_tool_registry.py`
  - Add three read-local tools:
    - `extract_research_constructs`
    - `diagnose_research_gaps`
    - `generate_research_ideas`

- Modify: `backend/routers/agent.py`
  - Dispatch the three new tools through existing `execute_tool(...)`.
  - Keep them read-only.

- Modify: `backend/services/research_agent_runtime.py`
  - Add economics/management intent detection.
  - Prefer idea-lab tools for prompts about theory, mechanisms, hypotheses, research gaps, identification strategies, and topic ideas.
  - Preserve current result-set and analysis-cache behavior.

- Create: `backend/tests/test_research_idea_lab.py`
  - Unit tests for pure service behavior.

- Modify: `backend/tests/test_agent_tool_registry.py`
  - Verify new tools are registered as read-local and non-writing.

- Modify: `backend/tests/test_research_agent_runtime.py`
  - Verify new intent detection and tool recommendations.

- Modify: `docs/RESEARCH_AGENT_IMPLEMENTATION.md`
  - Document the idea-lab tools and evidence discipline.

## Data Contracts

Use plain dictionaries in returned JSON so the existing agent tooling can serialize responses without new framework dependencies.

### ResearchConstructNote

```python
{
    "construct_id": "construct_1",
    "name": "数字化能力",
    "category": "construct",
    "definition": "A concise definition grounded in available evidence.",
    "mechanisms": ["resource orchestration", "information-processing improvement"],
    "variables": {
        "independent": ["digital capability"],
        "dependent": ["firm performance"],
        "mediators": ["innovation efficiency"],
        "moderators": ["market turbulence"],
    },
    "empirical_design": {
        "data_sources": ["annual reports", "firm panel data"],
        "identification": ["fixed effects", "DID if policy shock exists"],
        "risks": ["reverse causality", "measurement error"],
    },
    "evidence": [
        {
            "entry_id": "entry-1",
            "title": "Paper title",
            "source_tier": "P0",
            "source_kind": "abstract",
            "quote": "Short evidence snippet",
        }
    ],
    "uncertainty": "low|medium|high",
}
```

### EvidenceGap

```python
{
    "gap_id": "gap_1",
    "gap_type": "theory|mechanism|empirical_design|context|measurement|causal_identification",
    "summary": "What is missing or weak in the current evidence set.",
    "why_it_matters": "Why the gap can support a research contribution.",
    "supporting_evidence": [{"entry_id": "entry-1", "source_tier": "P0", "quote": "..."}],
    "needed_evidence": ["more original-text evidence on mechanisms", "data source for city-level policy shock"],
    "confidence": "low|medium|high",
}
```

### IdeaCandidate

```python
{
    "idea_id": "idea_1",
    "title": "数字化能力如何影响农业企业韧性？",
    "research_question": "A specific economics/management research question.",
    "theory_base": ["resource-based view", "dynamic capabilities"],
    "mechanism_chain": ["digital capability", "information processing", "supply-chain resilience"],
    "hypotheses": [
        "H1: Digital capability improves firm resilience.",
        "H2: Innovation efficiency mediates this relationship.",
    ],
    "data_strategy": {
        "sample": "A-share agricultural listed firms",
        "variables": ["digital capability", "resilience", "innovation efficiency"],
        "identification": "Firm and year fixed effects; explore policy shock if available.",
    },
    "contribution": ["mechanism contribution", "context contribution"],
    "risks": ["endogeneity", "construct measurement"],
    "evidence_refs": ["entry-1", "entry-2"],
    "confidence": "low|medium|high",
}
```

---

### Task 1: Add Pure Idea-Lab Service Skeleton

**Files:**
- Create: `backend/services/research_idea_lab.py`
- Test: `backend/tests/test_research_idea_lab.py`

- [ ] **Step 1: Write failing tests for construct extraction from evidence**

Add this test file:

```python
from __future__ import annotations

import unittest

from services.research_idea_lab import extract_constructs_from_evidence


class ResearchIdeaLabTests(unittest.TestCase):
    def test_extract_constructs_uses_evidence_terms_and_preserves_sources(self) -> None:
        evidence_pack = {
            "entries": [
                {
                    "entry_id": "entry-1",
                    "title": "Digital Capability and Firm Resilience",
                    "evidence": [
                        {
                            "source_tier": "P0",
                            "source_kind": "abstract",
                            "text": "Digital capability improves firm resilience through innovation efficiency.",
                        },
                        {
                            "source_tier": "P1",
                            "source_kind": "user_note",
                            "text": "Potential mediator: innovation efficiency. Risk: reverse causality.",
                        },
                    ],
                }
            ]
        }

        result = extract_constructs_from_evidence(
            evidence_pack=evidence_pack,
            topic="digital capability and firm resilience",
            max_constructs=5,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["topic"], "digital capability and firm resilience")
        self.assertGreaterEqual(len(result["constructs"]), 1)
        first = result["constructs"][0]
        self.assertIn("name", first)
        self.assertIn("evidence", first)
        self.assertEqual(first["evidence"][0]["entry_id"], "entry-1")
        self.assertEqual(first["evidence"][0]["source_tier"], "P0")
        self.assertIn("limitations", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
python -m unittest backend.tests.test_research_idea_lab
```

Expected: failure because `services.research_idea_lab` does not exist.

- [ ] **Step 3: Implement minimal service skeleton**

Create `backend/services/research_idea_lab.py`:

```python
"""Economics/management research idea helpers built on local evidence packs."""
from __future__ import annotations

import re
from typing import Any


ECON_MANAGEMENT_HINTS = {
    "mechanism": ("mechanism", "through", "mediate", "mediator", "路径", "机制", "中介"),
    "moderator": ("moderate", "moderator", "contingent", "边界", "调节"),
    "identification": ("did", "iv", "fixed effects", "instrument", "识别", "内生性", "固定效应"),
    "data": ("data", "sample", "panel", "dataset", "样本", "数据"),
}


def _compact(value: str | None) -> str:
    return " ".join((value or "").split())


def _tokenize(text: str) -> list[str]:
    return [part.lower() for part in re.findall(r"[A-Za-z][A-Za-z-]{2,}|[\u4e00-\u9fff]{2,}", text or "")]


def _entry_evidence(entry: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = entry.get("evidence") or entry.get("items") or []
    rows: list[dict[str, Any]] = []
    for row in evidence:
        text = _compact(row.get("text") or row.get("quote") or row.get("content"))
        if not text:
            continue
        rows.append(
            {
                "entry_id": str(entry.get("entry_id") or entry.get("id") or ""),
                "title": _compact(entry.get("title")),
                "source_tier": row.get("source_tier") or "P2",
                "source_kind": row.get("source_kind") or "unknown",
                "quote": text[:700],
            }
        )
    return rows


def _infer_construct_name(topic: str, text: str) -> str:
    topic_terms = _tokenize(topic)
    text_terms = _tokenize(text)
    for term in topic_terms:
        if term in text_terms:
            return term
    return text_terms[0] if text_terms else "research construct"


def extract_constructs_from_evidence(
    *,
    evidence_pack: dict[str, Any],
    topic: str,
    max_constructs: int = 8,
) -> dict[str, Any]:
    """Extract lightweight construct notes from an existing evidence pack.

    This first version is deterministic and conservative. It organizes evidence for
    later LLM synthesis without claiming unsupported novelty.
    """
    entries = evidence_pack.get("entries") or []
    constructs: list[dict[str, Any]] = []
    limitations: list[str] = []

    for entry in entries:
        rows = _entry_evidence(entry)
        if not rows:
            limitations.append(f"{entry.get('title') or entry.get('entry_id')}: no usable evidence snippets")
            continue
        combined = " ".join(row["quote"] for row in rows)
        name = _infer_construct_name(topic, combined)
        constructs.append(
            {
                "construct_id": f"construct_{len(constructs) + 1}",
                "name": name,
                "category": "construct",
                "definition": combined[:500],
                "mechanisms": _extract_hint_phrases(combined, "mechanism"),
                "variables": {"independent": [], "dependent": [], "mediators": [], "moderators": []},
                "empirical_design": {
                    "data_sources": _extract_hint_phrases(combined, "data"),
                    "identification": _extract_hint_phrases(combined, "identification"),
                    "risks": [],
                },
                "evidence": rows[:5],
                "uncertainty": "medium",
            }
        )
        if len(constructs) >= max(1, max_constructs):
            break

    return {
        "status": "ready",
        "topic": topic,
        "constructs": constructs,
        "limitations": limitations,
    }


def _extract_hint_phrases(text: str, hint_type: str) -> list[str]:
    lowered = text.lower()
    hits = [hint for hint in ECON_MANAGEMENT_HINTS[hint_type] if hint.lower() in lowered]
    return hits[:5]
```

- [ ] **Step 4: Run the test and verify it passes**

Run:

```powershell
python -m unittest backend.tests.test_research_idea_lab
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/research_idea_lab.py backend/tests/test_research_idea_lab.py
git commit -m "feat: add economics research idea lab service"
```

---

### Task 2: Add Gap Diagnosis And Idea Candidate Generation

**Files:**
- Modify: `backend/services/research_idea_lab.py`
- Modify: `backend/tests/test_research_idea_lab.py`

- [ ] **Step 1: Add failing tests for gaps and ideas**

Append these tests inside `ResearchIdeaLabTests`:

```python
    def test_diagnose_research_gaps_flags_missing_identification(self) -> None:
        from services.research_idea_lab import diagnose_research_gaps

        construct_result = {
            "constructs": [
                {
                    "construct_id": "construct_1",
                    "name": "digital capability",
                    "definition": "Digital capability may improve firm resilience.",
                    "mechanisms": ["through"],
                    "empirical_design": {"data_sources": [], "identification": [], "risks": []},
                    "evidence": [{"entry_id": "entry-1", "source_tier": "P0", "quote": "Digital capability improves resilience."}],
                }
            ]
        }

        result = diagnose_research_gaps(construct_result=construct_result, topic="digital capability")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["gaps"][0]["gap_type"], "causal_identification")
        self.assertIn("identification", result["gaps"][0]["needed_evidence"][0].lower())

    def test_generate_research_ideas_uses_constructs_and_gaps(self) -> None:
        from services.research_idea_lab import generate_research_ideas

        construct_result = {
            "topic": "digital capability",
            "constructs": [
                {
                    "construct_id": "construct_1",
                    "name": "digital capability",
                    "definition": "Digital capability improves resilience through innovation efficiency.",
                    "mechanisms": ["through"],
                    "evidence": [{"entry_id": "entry-1", "source_tier": "P0", "quote": "Digital capability improves resilience."}],
                }
            ],
        }
        gap_result = {
            "gaps": [
                {
                    "gap_id": "gap_1",
                    "gap_type": "mechanism",
                    "summary": "The mediating mechanism is under-specified.",
                    "confidence": "medium",
                }
            ]
        }

        result = generate_research_ideas(
            construct_result=construct_result,
            gap_result=gap_result,
            max_ideas=3,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["ideas"]), 1)
        idea = result["ideas"][0]
        self.assertIn("research_question", idea)
        self.assertIn("hypotheses", idea)
        self.assertEqual(idea["evidence_refs"], ["entry-1"])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m unittest backend.tests.test_research_idea_lab
```

Expected: failure because the two functions do not exist.

- [ ] **Step 3: Implement gap and idea functions**

Append to `backend/services/research_idea_lab.py`:

```python
def diagnose_research_gaps(*, construct_result: dict[str, Any], topic: str) -> dict[str, Any]:
    """Diagnose conservative evidence gaps from construct notes."""
    gaps: list[dict[str, Any]] = []
    for construct in construct_result.get("constructs") or []:
        evidence = construct.get("evidence") or []
        empirical = construct.get("empirical_design") or {}
        if not empirical.get("identification"):
            gaps.append(
                {
                    "gap_id": f"gap_{len(gaps) + 1}",
                    "gap_type": "causal_identification",
                    "summary": f"{construct.get('name')}: causal identification is not yet explicit in the retrieved evidence.",
                    "why_it_matters": "Economics and management claims need a credible design before the idea can become a research plan.",
                    "supporting_evidence": evidence[:3],
                    "needed_evidence": ["identification strategy evidence", "data source and variation source"],
                    "confidence": "medium",
                }
            )
        if construct.get("mechanisms") == []:
            gaps.append(
                {
                    "gap_id": f"gap_{len(gaps) + 1}",
                    "gap_type": "mechanism",
                    "summary": f"{construct.get('name')}: mechanism chain is weak or absent.",
                    "why_it_matters": "A clear mechanism supports theory contribution and testable hypotheses.",
                    "supporting_evidence": evidence[:3],
                    "needed_evidence": ["mechanism evidence", "mediator or moderator discussion"],
                    "confidence": "medium",
                }
            )
    return {"status": "ready", "topic": topic, "gaps": gaps, "limitations": construct_result.get("limitations") or []}


def generate_research_ideas(
    *,
    construct_result: dict[str, Any],
    gap_result: dict[str, Any],
    max_ideas: int = 5,
) -> dict[str, Any]:
    """Generate structured economics/management idea candidates from constructs and gaps."""
    constructs = construct_result.get("constructs") or []
    gaps = gap_result.get("gaps") or []
    ideas: list[dict[str, Any]] = []

    for construct in constructs[: max(1, max_ideas)]:
        name = construct.get("name") or "research construct"
        evidence_refs = []
        for row in construct.get("evidence") or []:
            entry_id = row.get("entry_id")
            if entry_id and entry_id not in evidence_refs:
                evidence_refs.append(entry_id)
        related_gap = gaps[0] if gaps else {}
        ideas.append(
            {
                "idea_id": f"idea_{len(ideas) + 1}",
                "title": f"How does {name} shape economic or management outcomes?",
                "research_question": f"How does {name} affect the focal outcome, and through which mechanism?",
                "theory_base": [],
                "mechanism_chain": [name] + list(construct.get("mechanisms") or []),
                "hypotheses": [
                    f"H1: {name} is associated with the focal economic or management outcome.",
                    "H2: The relationship operates through the mechanism identified in the evidence set.",
                ],
                "data_strategy": {
                    "sample": "",
                    "variables": [name],
                    "identification": "Use the evidence gaps to choose fixed effects, DID, IV, or another credible design.",
                },
                "contribution": ["theory contribution", "empirical design contribution"],
                "risks": [related_gap.get("summary")] if related_gap else [],
                "evidence_refs": evidence_refs,
                "confidence": "medium" if evidence_refs else "low",
            }
        )

    return {"status": "ready", "topic": construct_result.get("topic") or "", "ideas": ideas, "gaps": gaps}
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest backend.tests.test_research_idea_lab
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/research_idea_lab.py backend/tests/test_research_idea_lab.py
git commit -m "feat: generate research gaps and idea candidates"
```

---

### Task 3: Register Read-Only Idea-Lab Tools

**Files:**
- Modify: `backend/services/agent_tool_registry.py`
- Modify: `backend/tests/test_agent_tool_registry.py`

- [ ] **Step 1: Add failing registry tests**

Append to `AgentToolRegistryTests` in `backend/tests/test_agent_tool_registry.py`:

```python
    def test_idea_lab_tools_are_read_only(self) -> None:
        construct_tool = get_tool("extract_research_constructs")
        gap_tool = get_tool("diagnose_research_gaps")
        idea_tool = get_tool("generate_research_ideas")

        for tool in (construct_tool, gap_tool, idea_tool):
            self.assertEqual(tool.permission, "read_local")
            self.assertFalse(tool.consent_required)
            self.assertFalse(tool.proposal_required)
            self.assertFalse(tool.writes_database)
            self.assertFalse(tool.uses_internet)

    def test_extract_research_constructs_requires_topic(self) -> None:
        tool = get_tool("extract_research_constructs")
        self.assertIn("topic", tool.schema["required"])
        self.assertIn("entry_ids", tool.schema["properties"])
```

- [ ] **Step 2: Run registry tests and verify failure**

Run:

```powershell
python -m unittest backend.tests.test_agent_tool_registry
```

Expected: failure because new tool names are not registered.

- [ ] **Step 3: Add tool registry entries**

In `backend/services/agent_tool_registry.py`, add these entries to `AGENT_TOOLS` near `analyze_reading_candidates`:

```python
    AgentTool(
        name="extract_research_constructs",
        description=(
            "Extract economics/management research constructs, mechanisms, variables, "
            "and empirical design hints from local evidence packs or selected bibliography entries."
        ),
        permission="read_local",
        handler="extract_research_constructs",
        schema=_object(
            {
                "topic": {"type": "string"},
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "max_constructs": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            ["topic"],
        ),
    ),
    AgentTool(
        name="diagnose_research_gaps",
        description=(
            "Diagnose theory, mechanism, measurement, context, and causal-identification gaps "
            "from previously extracted economics/management constructs."
        ),
        permission="read_local",
        handler="diagnose_research_gaps",
        schema=_object(
            {
                "topic": {"type": "string"},
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "max_constructs": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            ["topic"],
        ),
    ),
    AgentTool(
        name="generate_research_ideas",
        description=(
            "Generate structured economics/management research idea candidates from local constructs "
            "and evidence gaps, including research question, hypotheses, data strategy, contribution, and risks."
        ),
        permission="read_local",
        handler="generate_research_ideas",
        schema=_object(
            {
                "topic": {"type": "string"},
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "max_ideas": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            ["topic"],
        ),
    ),
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest backend.tests.test_agent_tool_registry
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/agent_tool_registry.py backend/tests/test_agent_tool_registry.py
git commit -m "feat: register economics idea lab tools"
```

---

### Task 4: Dispatch Tools Through Agent Router

**Files:**
- Modify: `backend/routers/agent.py`
- Test: `backend/tests/test_research_idea_lab.py`

- [ ] **Step 1: Add a service-level integration helper test**

Append to `backend/tests/test_research_idea_lab.py`:

```python
    def test_run_idea_lab_pipeline_composes_constructs_gaps_and_ideas(self) -> None:
        from services.research_idea_lab import run_idea_lab_pipeline

        evidence_pack = {
            "entries": [
                {
                    "entry_id": "entry-1",
                    "title": "Digital Capability and Firm Resilience",
                    "evidence": [
                        {
                            "source_tier": "P0",
                            "source_kind": "abstract",
                            "text": "Digital capability improves firm resilience through innovation efficiency.",
                        }
                    ],
                }
            ]
        }

        result = run_idea_lab_pipeline(
            evidence_pack=evidence_pack,
            topic="digital capability",
            max_constructs=5,
            max_ideas=3,
        )

        self.assertEqual(result["status"], "ready")
        self.assertIn("constructs", result)
        self.assertIn("gaps", result)
        self.assertIn("ideas", result)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m unittest backend.tests.test_research_idea_lab
```

Expected: failure because `run_idea_lab_pipeline` does not exist.

- [ ] **Step 3: Add pipeline helper**

Append to `backend/services/research_idea_lab.py`:

```python
def run_idea_lab_pipeline(
    *,
    evidence_pack: dict[str, Any],
    topic: str,
    max_constructs: int = 8,
    max_ideas: int = 5,
) -> dict[str, Any]:
    construct_result = extract_constructs_from_evidence(
        evidence_pack=evidence_pack,
        topic=topic,
        max_constructs=max_constructs,
    )
    gap_result = diagnose_research_gaps(construct_result=construct_result, topic=topic)
    idea_result = generate_research_ideas(
        construct_result=construct_result,
        gap_result=gap_result,
        max_ideas=max_ideas,
    )
    return {
        "status": "ready",
        "topic": topic,
        "constructs": construct_result.get("constructs") or [],
        "gaps": gap_result.get("gaps") or [],
        "ideas": idea_result.get("ideas") or [],
        "limitations": construct_result.get("limitations") or [],
    }
```

- [ ] **Step 4: Wire router dispatch**

In `backend/routers/agent.py`, import the helper near the other service imports:

```python
from services.research_idea_lab import (
    diagnose_research_gaps as idea_lab_diagnose_research_gaps,
    extract_constructs_from_evidence,
    generate_research_ideas as idea_lab_generate_research_ideas,
    run_idea_lab_pipeline,
)
```

In `execute_tool(...)`, add cases after `get_evidence_pack` / `research_search` handling:

```python
    if name == "extract_research_constructs":
        pack = await get_evidence_pack(
            db,
            owner_user_id=user.id,
            query=_research_query_from_args(
                {
                    "question": args.get("topic") or "",
                    "entry_ids": args.get("entry_ids") or [],
                    "keywords": args.get("keywords") or [],
                    "limit_entries": 0 if args.get("entry_ids") else 50,
                    "limit_evidence_per_entry": 5,
                    "include_source_text": True,
                    "include_user_notes": True,
                    "include_ai_notes": True,
                }
            ),
        )
        return extract_constructs_from_evidence(
            evidence_pack=pack,
            topic=args.get("topic") or "",
            max_constructs=int(args.get("max_constructs") or 8),
        )
    if name == "diagnose_research_gaps":
        pack = await get_evidence_pack(
            db,
            owner_user_id=user.id,
            query=_research_query_from_args(
                {
                    "question": args.get("topic") or "",
                    "entry_ids": args.get("entry_ids") or [],
                    "limit_entries": 0 if args.get("entry_ids") else 50,
                    "limit_evidence_per_entry": 5,
                    "include_source_text": True,
                    "include_user_notes": True,
                    "include_ai_notes": True,
                }
            ),
        )
        constructs = extract_constructs_from_evidence(
            evidence_pack=pack,
            topic=args.get("topic") or "",
            max_constructs=int(args.get("max_constructs") or 8),
        )
        return idea_lab_diagnose_research_gaps(
            construct_result=constructs,
            topic=args.get("topic") or "",
        )
    if name == "generate_research_ideas":
        pack = await get_evidence_pack(
            db,
            owner_user_id=user.id,
            query=_research_query_from_args(
                {
                    "question": args.get("topic") or "",
                    "entry_ids": args.get("entry_ids") or [],
                    "limit_entries": 0 if args.get("entry_ids") else 50,
                    "limit_evidence_per_entry": 5,
                    "include_source_text": True,
                    "include_user_notes": True,
                    "include_ai_notes": True,
                }
            ),
        )
        return run_idea_lab_pipeline(
            evidence_pack=pack,
            topic=args.get("topic") or "",
            max_constructs=8,
            max_ideas=int(args.get("max_ideas") or 5),
        )
```

- [ ] **Step 5: Run targeted tests**

Run:

```powershell
python -m unittest backend.tests.test_research_idea_lab backend.tests.test_agent_tool_registry
python -m py_compile backend\services\research_idea_lab.py backend\routers\agent.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/routers/agent.py backend/services/research_idea_lab.py backend/tests/test_research_idea_lab.py
git commit -m "feat: dispatch economics idea lab tools"
```

---

### Task 5: Add Runtime Intent And Tool Guidance

**Files:**
- Modify: `backend/services/research_agent_runtime.py`
- Modify: `backend/tests/test_research_agent_runtime.py`

- [ ] **Step 1: Add failing runtime tests**

Append to `ResearchAgentRuntimeTests`:

```python
    def test_build_task_frame_detects_research_idea_intent(self) -> None:
        frame = build_task_frame("基于这些文献帮我生成几个经济管理研究选题和机制假说", {})
        self.assertEqual(frame["intent"], "generate_research_ideas")
        self.assertTrue(frame["prefers_idea_lab_tools"])

    def test_runtime_prompt_recommends_idea_lab_tools(self) -> None:
        frame = build_task_frame("从这些论文里提取理论概念、机制和识别策略", {})
        prompts = build_runtime_system_prompts(frame, {}, {})
        combined = "\n".join(prompts)
        self.assertIn("extract_research_constructs", combined)
        self.assertIn("diagnose_research_gaps", combined)
        self.assertIn("generate_research_ideas", combined)
```

- [ ] **Step 2: Run runtime tests and verify failure**

Run:

```powershell
python -m unittest backend.tests.test_research_agent_runtime
```

Expected: failure because the intent and prompt guidance do not exist.

- [ ] **Step 3: Add intent patterns**

In `backend/services/research_agent_runtime.py`, add near the existing pattern constants:

```python
IDEA_LAB_PATTERNS = (
    "研究选题",
    "研究想法",
    "研究问题",
    "理论概念",
    "理论机制",
    "机制假说",
    "研究假设",
    "识别策略",
    "理论缺口",
    "文献缺口",
    "变量关系",
    "经济管理",
    "管理学",
    "经济学",
    "research idea",
    "research question",
    "theoretical construct",
    "mechanism",
    "hypothesis",
    "identification strategy",
    "research gap",
)
```

In `build_task_frame(...)`, after count/status/execution checks but before generic summary fallback, add:

```python
    if _contains_any(message, IDEA_LAB_PATTERNS):
        frame["intent"] = "generate_research_ideas"
        frame["prefers_idea_lab_tools"] = True
        frame["prefers_result_set_tools"] = True
```

Use the local variable name that already exists in the function for the raw message. If the function uses `raw_message`, apply `_contains_any(raw_message, IDEA_LAB_PATTERNS)`.

- [ ] **Step 4: Add runtime prompt guidance**

In `build_runtime_system_prompts(...)`, add:

```python
    if task_frame.get("prefers_idea_lab_tools"):
        prompts.append(
            "本轮是经济管理研究构思/理论机制/假设/识别策略场景。优先使用 "
            "extract_research_constructs、diagnose_research_gaps、generate_research_ideas。"
            "回答必须区分 P0 原文/题录证据、P1 用户笔记、P2 AI 笔记；不要把缺少证据的推断写成事实。"
        )
```

- [ ] **Step 5: Run runtime tests**

Run:

```powershell
python -m unittest backend.tests.test_research_agent_runtime
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/services/research_agent_runtime.py backend/tests/test_research_agent_runtime.py
git commit -m "feat: route research idea prompts to idea lab"
```

---

### Task 6: Persist Idea-Lab Results In Runtime State

**Files:**
- Modify: `backend/services/research_agent_runtime.py`
- Modify: `backend/tests/test_research_agent_runtime.py`

- [ ] **Step 1: Add failing state update test**

Append to `ResearchAgentRuntimeTests`:

```python
    def test_update_state_after_tool_stores_last_idea_lab_result(self) -> None:
        state = {}
        result = {
            "status": "ready",
            "topic": "digital capability",
            "constructs": [{"construct_id": "construct_1", "name": "digital capability"}],
            "gaps": [{"gap_id": "gap_1", "gap_type": "causal_identification"}],
            "ideas": [{"idea_id": "idea_1", "title": "Idea"}],
        }

        updated = update_state_after_tool(
            state,
            "generate_research_ideas",
            {"topic": "digital capability"},
            result,
        )

        self.assertIn("last_idea_lab_result", updated)
        self.assertEqual(updated["last_idea_lab_result"]["topic"], "digital capability")
        self.assertEqual(updated["last_idea_lab_result"]["idea_count"], 1)
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m unittest backend.tests.test_research_agent_runtime
```

Expected: failure because state update does not store idea-lab summaries.

- [ ] **Step 3: Update runtime state handling**

In `update_state_after_tool(...)`, add:

```python
    if name in {"extract_research_constructs", "diagnose_research_gaps", "generate_research_ideas"} and isinstance(result, dict):
        state["last_idea_lab_result"] = {
            "tool": name,
            "topic": result.get("topic") or args.get("topic"),
            "construct_count": len(result.get("constructs") or []),
            "gap_count": len(result.get("gaps") or []),
            "idea_count": len(result.get("ideas") or []),
            "constructs": (result.get("constructs") or [])[:10],
            "gaps": (result.get("gaps") or [])[:10],
            "ideas": (result.get("ideas") or [])[:10],
        }
```

Place it near the existing state updates for result sets and analysis cache.

- [ ] **Step 4: Surface state in UI summary**

In `summarize_state_for_ui(...)`, include:

```python
    if state.get("last_idea_lab_result"):
        summary["last_idea_lab_result"] = state["last_idea_lab_result"]
```

- [ ] **Step 5: Run runtime tests**

Run:

```powershell
python -m unittest backend.tests.test_research_agent_runtime
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/services/research_agent_runtime.py backend/tests/test_research_agent_runtime.py
git commit -m "feat: persist idea lab runtime state"
```

---

### Task 7: Documentation

**Files:**
- Modify: `docs/RESEARCH_AGENT_IMPLEMENTATION.md`

- [ ] **Step 1: Add documentation section**

Add this section after the current tool registry section:

```markdown
### Economics/Management Idea Lab Tools

The research agent includes read-only tools for economics and management research ideation. These tools are designed for local evidence synthesis and do not run code, modify the database, or perform external search.

| Tool | Permission | Purpose |
|---|---|---|
| `extract_research_constructs` | `read_local` | Extract theoretical constructs, mechanisms, variables, empirical-design hints, and source-backed evidence from selected literature. |
| `diagnose_research_gaps` | `read_local` | Identify theory, mechanism, measurement, context, and causal-identification gaps from extracted constructs. |
| `generate_research_ideas` | `read_local` | Generate structured research idea candidates with question, hypotheses, data strategy, contribution, risks, and evidence references. |

Evidence discipline:

- P0 evidence remains the strongest source: original text windows, title, abstract, DOI, metadata, and exact source evidence.
- P1 evidence includes user notes, edits, annotations, and card notes.
- P2 AI-generated reading notes may guide synthesis but cannot override P0/P1.
- If a proposed idea depends on missing evidence, the tool must report it as a gap or risk.

The idea-lab workflow is inspired by AI-Researcher's concept-decomposition pattern but is adapted to economics and management research. It does not import AI-Researcher's Docker execution, ML code agents, or ChromaDB memory.
```

- [ ] **Step 2: Run a doc grep sanity check**

Run:

```powershell
rg -n "extract_research_constructs|diagnose_research_gaps|generate_research_ideas" docs\RESEARCH_AGENT_IMPLEMENTATION.md
```

Expected: all three tool names appear.

- [ ] **Step 3: Commit**

```powershell
git add docs/RESEARCH_AGENT_IMPLEMENTATION.md
git commit -m "docs: document economics idea lab tools"
```

---

### Task 8: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run targeted test suite**

Run:

```powershell
python -m unittest backend.tests.test_research_idea_lab backend.tests.test_agent_tool_registry backend.tests.test_research_agent_runtime backend.tests.test_research_retrieval
```

Expected: all pass.

- [ ] **Step 2: Run compile check**

Run:

```powershell
python -m py_compile backend\services\research_idea_lab.py backend\services\agent_tool_registry.py backend\services\research_agent_runtime.py backend\routers\agent.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 4: Manual product smoke test**

In the running app, ask the research agent:

```text
基于上一轮这些文献，帮我提取经济管理研究中的理论概念、机制假说和可能的识别策略，再生成 3 个研究选题。
```

Expected:

- Agent prefers `extract_research_constructs`, `diagnose_research_gaps`, or `generate_research_ideas`.
- It does not call external tools unless the user explicitly asks for external search.
- It cites local evidence tiers or clearly marks gaps.
- It does not claim unsupported novelty as fact.

- [ ] **Step 5: Final commit if verification required fixes**

```powershell
git status --short
git add backend docs
git commit -m "test: verify economics idea lab workflow"
```

Only commit if Step 1-4 required additional edits.

---

## Rollout Notes

This feature is safe to ship behind existing research-agent behavior because:

- All new tools are read-local.
- No database writes are introduced in the first version.
- No external search is introduced.
- No Docker or local command execution is introduced.
- Existing P0/P1/P2 evidence rules remain intact.

Recommended rollout:

1. Implement service and tests locally.
2. Add tools to registry.
3. Add runtime routing.
4. Test in local app with a small selected result set.
5. Deploy only after targeted tests pass.

## Follow-Up Ideas Not In This Plan

- Persist full `ResearchConstructNote` rows in the database.
- Add UI cards for constructs, gaps, and ideas.
- Add user-confirmed "save idea to project notebook" proposal action.
- Add external discovery for missing theory or data gaps after explicit consent.
- Add citation formatting for generated idea reports.

## Self-Review

Spec coverage:

- Reads AI-Researcher for useful parts: covered by concept decomposition and idea generation pattern.
- Adapts to economics/management: covered by construct, gap, and idea schemas.
- Reuses existing `deep-reading-agent-online` architecture: covered by `research_retrieval`, runtime, and registry integration.
- Avoids unsafe migration: Docker, code execution, ChromaDB, and GitHub search are explicitly out of scope.

Placeholder scan:

- No task uses TBD or vague "add validation" instructions.
- Each code task includes concrete test or implementation snippets.

Type consistency:

- Tool names are consistent: `extract_research_constructs`, `diagnose_research_gaps`, `generate_research_ideas`.
- State key is consistent: `last_idea_lab_result`.
- Returned payload keys are consistent: `constructs`, `gaps`, `ideas`, `limitations`.
