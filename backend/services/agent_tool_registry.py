"""OpenAI-compatible research agent tool registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentTool:
    name: str
    description: str
    permission: str
    schema: dict[str, Any]
    consent_required: bool = False
    proposal_required: bool = False
    writes_database: bool = False
    uses_internet: bool = False
    handler: str | None = None

    def as_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }

    def as_capability(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission,
            "consent_required": self.consent_required,
            "proposal_required": self.proposal_required,
            "writes_database": self.writes_database,
            "uses_internet": self.uses_internet,
        }


def _object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


AGENT_TOOLS = [
    AgentTool(
        name="research_search",
        description=(
            "Search the user's tiered literature knowledge base across metadata, abstracts, "
            "user notes, edited reading notes, AI reading notes, cards, annotations, references, and source windows."
        ),
        permission="read_local",
        handler="research_search",
        schema=_object(
            {
                "question": {"type": "string"},
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "include_source_text": {"type": "boolean"},
                "include_user_notes": {"type": "boolean"},
                "include_ai_notes": {"type": "boolean"},
                "limit_entries": {"type": "integer", "minimum": 0, "description": "Max entries to search. 0 = search all entries."},
                "limit_evidence_per_entry": {"type": "integer", "minimum": 1},
            },
            ["question"],
        ),
    ),
    AgentTool(
        name="analyze_writing_style",
        description=(
            "Retrieve local original Markdown passages for writing-style analysis of an author, journal, "
            "paper, introduction, theory section, methods section, or argument structure."
        ),
        permission="read_local",
        handler="analyze_writing_style",
        schema=_object(
            {
                "question": {"type": "string"},
                "author_or_journal": {"type": "string"},
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "section_type": {"type": "string", "enum": ["", "introduction", "theory", "method", "general"]},
                "limit_entries": {"type": "integer", "minimum": 1, "maximum": 20},
                "max_sections_per_entry": {"type": "integer", "minimum": 1, "maximum": 12},
            },
            ["question"],
        ),
    ),
    AgentTool(
        name="get_evidence_pack",
        description="Return P0/P1/P2 evidence packs for selected entries and a research question.",
        permission="read_local",
        handler="get_evidence_pack",
        schema=_object(
            {
                "question": {"type": "string"},
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "include_source_text": {"type": "boolean"},
                "include_user_notes": {"type": "boolean"},
                "include_ai_notes": {"type": "boolean"},
                "limit_entries": {"type": "integer", "minimum": 0, "description": "Max entries to search. 0 = search all entries."},
                "limit_evidence_per_entry": {"type": "integer", "minimum": 1},
            },
            ["question"],
        ),
    ),
    AgentTool(
        name="get_source_windows",
        description="Fetch local original Markdown source text windows for selected bibliography entries.",
        permission="read_local",
        handler="get_source_windows",
        schema=_object(
            {
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "question": {"type": "string"},
                "max_windows_per_entry": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            ["entry_ids"],
        ),
    ),
    AgentTool(
        name="search_cnki",
        description=(
            "Build CNKI title-search URLs for selected Chinese bibliography entries or provided titles. "
            "Returns a batch of URLs that the frontend can open in new browser tabs."
        ),
        permission="external_read",
        consent_required=True,
        uses_internet=True,
        handler="search_cnki",
        schema=_object(
            {
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "titles": {"type": "array", "items": {"type": "string"}},
                "max_items": {"type": "integer", "minimum": 1},
            },
        ),
    ),
    AgentTool(
        name="lookup_english_fulltext",
        description=(
            "Look up English full-text candidates through existing OpenAlex, Unpaywall, Semantic Scholar, "
            "Google PDF, and working-paper search helpers. Does not attach PDFs or write to the database."
        ),
        permission="external_read",
        consent_required=True,
        uses_internet=True,
        handler="lookup_english_fulltext",
        schema=_object(
            {
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "max_entries": {"type": "integer", "minimum": 1},
            },
            ["entry_ids"],
        ),
    ),
    AgentTool(
        name="search_library",
        description="Search the user's bibliography library by title, abstract, journal, keyword, or tag.",
        permission="read_local",
        handler="search_library",
        schema=_object(
            {
                "query": {"type": "string"},
                "reading_status": {"type": "string", "enum": ["", "none", "has_pdf", "reading", "read"]},
                "limit": {"type": "integer", "minimum": 1},
            }
        ),
    ),
    AgentTool(
        name="count_library",
        description=(
            "Count matching bibliography entries in the user's library without listing all titles. "
            "Use this for questions about how many papers/items exist under current filters."
        ),
        permission="read_local",
        handler="count_library",
        schema=_object(
            {
                "query": {"type": "string"},
                "reading_status": {"type": "string", "enum": ["", "none", "has_pdf", "reading", "read"]},
            }
        ),
    ),
    AgentTool(
        name="analyze_reading_candidates",
        description=(
            "Analyze a large collection of library papers in batches, write structured working notes, "
            "and recommend which papers should be prioritized for deep reading."
        ),
        permission="read_local",
        handler="analyze_reading_candidates",
        schema=_object(
            {
                "topic": {"type": "string"},
                "query": {"type": "string"},
                "reading_status": {"type": "string", "enum": ["", "none", "has_pdf", "reading", "read"]},
                "batch_size": {"type": "integer", "minimum": 20, "maximum": 200},
                "max_entries": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            ["topic"],
        ),
    ),
    AgentTool(
        name="filter_analysis_cache",
        description=(
            "Reuse the current session's persisted analysis cache and filter it by journal tier, theme cluster, "
            "full-text availability, or reading status without rescanning the full library."
        ),
        permission="read_local",
        handler="filter_analysis_cache",
        schema=_object(
            {
                "topic": {"type": "string"},
                "journal_tier_labels": {"type": "array", "items": {"type": "string"}},
                "cluster_labels": {"type": "array", "items": {"type": "string"}},
                "require_fulltext": {"type": "boolean"},
                "reading_status": {"type": "string", "enum": ["", "none", "has_pdf", "reading", "read"]},
                "max_entries": {"type": "integer", "minimum": 0, "maximum": 2000, "description": "0 = keep all filtered entries."},
            },
            ["topic"],
        ),
    ),
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
    ),    AgentTool(
        name="get_entry_detail",
        description="Get metadata, source file id, and recent workflow timeline for a bibliography entry.",
        permission="read_local",
        handler="get_entry_detail",
        schema=_object({"entry_id": {"type": "string"}}, ["entry_id"]),
    ),
    AgentTool(
        name="get_reading_context",
        description="Fetch structured deep-reading sections for selected entries so the assistant can compare or synthesize them.",
        permission="read_local",
        handler="get_reading_context",
        schema=_object(
            {
                "entry_ids": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string", "enum": ["", "long", "quant", "qual"]},
                "max_chars_per_item": {"type": "integer", "minimum": 300, "maximum": 8000},
            },
            ["entry_ids"],
        ),
    ),
    AgentTool(
        name="start_reading",
        description="Start a long, quantitative 7-step, or qualitative 4-step reading job for one PDF/Markdown file.",
        permission="propose_write",
        proposal_required=True,
        writes_database=True,
        handler="start_reading",
        schema=_object(
            {
                "mode": {"type": "string", "enum": ["long", "quant", "qual"]},
                "file_id": {"type": "string"},
                "entry_id": {"type": "string"},
                "analysis_dims": {"type": "array", "items": {"type": "string"}},
                "custom_question": {"type": "string"},
                "extraction_method": {"type": "string", "enum": ["full", "smart", "first_pages"]},
                "conflict_resolution": {
                    "type": "string",
                    "enum": ["check", "overwrite", "new", "incremental", "skip"],
                },
            },
            ["mode"],
        ),
    ),
    AgentTool(
        name="start_batch_reading",
        description="Start reading jobs for multiple file ids.",
        permission="propose_write",
        proposal_required=True,
        writes_database=True,
        handler="start_batch_reading",
        schema=_object(
            {
                "mode": {"type": "string", "enum": ["long", "quant", "qual"]},
                "file_ids": {"type": "array", "items": {"type": "string"}},
                "analysis_dims": {"type": "array", "items": {"type": "string"}},
                "custom_question": {"type": "string"},
                "extraction_method": {"type": "string", "enum": ["full", "smart", "first_pages"]},
                "conflict_resolution": {
                    "type": "string",
                    "enum": ["check", "overwrite", "new", "incremental", "skip"],
                },
            },
            ["mode", "file_ids"],
        ),
    ),
    AgentTool(
        name="scan_input_folder",
        description=(
            "Read-only scan of the user's uploaded AI assistant inbox batch and compare it with the user's library. "
            "Use this when the user asks to see, list, inspect, or tabulate papers. "
            "Use offset to continue the next batch after settling working notes. "
            "This never imports files and never starts reading jobs."
        ),
        permission="read_local",
        handler="scan_input_folder",
        schema=_object(
            {
                "topic": {"type": "string"},
                "recursive": {"type": "boolean"},
                "max_files": {"type": "integer", "minimum": 1, "maximum": 500},
                "offset": {"type": "integer", "minimum": 0},
                "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
            }
        ),
    ),
    AgentTool(
        name="import_folder_and_start_reading",
        description=(
            "Scan the user's uploaded AI assistant inbox batch, select papers related to a topic, "
            "and start batch reading jobs. Use only when the user explicitly asks to start/run/batch read/analyze."
        ),
        permission="propose_write",
        proposal_required=True,
        writes_database=True,
        handler="import_folder_and_start_reading",
        schema=_object(
            {
                "topic": {"type": "string"},
                "mode": {"type": "string", "enum": ["quant", "qual", "long"]},
                "recursive": {"type": "boolean"},
                "max_files": {"type": "integer", "minimum": 1, "maximum": 500},
                "offset": {"type": "integer", "minimum": 0},
                "confidence_threshold": {"type": "number", "minimum": 0, "maximum": 1},
                "conflict_resolution": {
                    "type": "string",
                    "enum": ["check", "overwrite", "new", "incremental", "skip"],
                },
                "analysis_dims": {"type": "array", "items": {"type": "string"}},
                "custom_question": {"type": "string"},
                "extraction_method": {"type": "string", "enum": ["full", "smart", "first_pages"]},
            },
            ["topic", "mode"],
        ),
    ),
    AgentTool(
        name="get_job_status",
        description="Get status and artifact links for a reading or synthesis job.",
        permission="read_local",
        handler="get_job_status",
        schema=_object({"job_id": {"type": "string"}}, ["job_id"]),
    ),
]


TOOL_MAP = {tool.name: tool for tool in AGENT_TOOLS}
TOOL_SCHEMAS = [tool.as_openai_schema() for tool in AGENT_TOOLS]


def get_tool(name: str) -> AgentTool:
    try:
        return TOOL_MAP[name]
    except KeyError as exc:
        raise KeyError(f"unknown_tool:{name}") from exc


def list_tool_capabilities() -> list[dict[str, Any]]:
    return [tool.as_capability() for tool in AGENT_TOOLS]


