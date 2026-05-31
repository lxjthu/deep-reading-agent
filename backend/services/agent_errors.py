from __future__ import annotations

from enum import Enum
from typing import Any


class AgentErrorCode(str, Enum):
    LLM_CONNECTION_ERROR = "llm_connection_error"
    LLM_TIMEOUT = "llm_timeout"
    LLM_AUTH_ERROR = "llm_auth_error"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_BAD_REQUEST = "llm_bad_request"
    LLM_UPSTREAM_ERROR = "llm_upstream_error"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    AGENT_RUNTIME_ERROR = "agent_runtime_error"
    INVALID_API_KEY = "invalid_api_key"
    PERMISSION_DENIED = "permission_denied"
    RESOURCE_NOT_FOUND = "resource_not_found"
    HTTP_ERROR = "http_error"
    CONSENT_REQUIRED = "consent_required"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONTEXT_RESOLUTION_FAILED = "context_resolution_failed"
    UPLOAD_ERROR = "upload_error"
    DB_ERROR = "db_error"


class ErrorStage(str, Enum):
    SESSION_SETUP = "session_setup"
    LLM_COMPLETION = "llm_completion"
    TOOL_EXECUTION = "tool_execution"
    PROPOSAL_EXECUTION = "proposal_execution"
    UPLOAD = "upload"
    INPUT_VALIDATION = "input_validation"
    PROVIDER_PROBE = "provider_probe"


class RuntimeNoticeCode(str, Enum):
    CONSENT_REQUIRED = "consent_required"
    EXTERNAL_CONSENT_REQUIRED = "external_consent_required"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CONTEXT_REQUIRED = "context_required"
    CONTINUATION_CONTEXT_REQUIRED = "continuation_context_required"
    INEFFICIENT_TOOL_PATH = "inefficient_tool_path"
    PREFER_RESULT_SET_TOOLS = "prefer_result_set_tools"
    PREFER_CONTEXTUAL_RESULT_SET = "prefer_contextual_result_set"
    ANALYSIS_CACHE_REQUIRED = "analysis_cache_required"
    PREFER_ANALYSIS_CACHE_FILTER = "prefer_analysis_cache_filter"
    PREFER_BATCH_ANALYSIS_TOOL = "prefer_batch_analysis_tool"
    DUPLICATE_TOOL_CALL_BLOCKED = "duplicate_tool_call_blocked"
    SEARCH_LIBRARY_BUDGET_EXHAUSTED = "search_library_budget_exhausted"


RUNTIME_NOTICE_TO_ERROR_CATEGORY: dict[RuntimeNoticeCode, AgentErrorCode] = {
    RuntimeNoticeCode.CONSENT_REQUIRED: AgentErrorCode.CONSENT_REQUIRED,
    RuntimeNoticeCode.EXTERNAL_CONSENT_REQUIRED: AgentErrorCode.CONSENT_REQUIRED,
    RuntimeNoticeCode.BUDGET_EXHAUSTED: AgentErrorCode.BUDGET_EXHAUSTED,
    RuntimeNoticeCode.DUPLICATE_TOOL_CALL_BLOCKED: AgentErrorCode.BUDGET_EXHAUSTED,
    RuntimeNoticeCode.SEARCH_LIBRARY_BUDGET_EXHAUSTED: AgentErrorCode.BUDGET_EXHAUSTED,
    RuntimeNoticeCode.CONTEXT_REQUIRED: AgentErrorCode.CONTEXT_RESOLUTION_FAILED,
    RuntimeNoticeCode.CONTINUATION_CONTEXT_REQUIRED: AgentErrorCode.CONTEXT_RESOLUTION_FAILED,
    RuntimeNoticeCode.ANALYSIS_CACHE_REQUIRED: AgentErrorCode.CONTEXT_RESOLUTION_FAILED,
    RuntimeNoticeCode.INEFFICIENT_TOOL_PATH: AgentErrorCode.AGENT_RUNTIME_ERROR,
    RuntimeNoticeCode.PREFER_RESULT_SET_TOOLS: AgentErrorCode.AGENT_RUNTIME_ERROR,
    RuntimeNoticeCode.PREFER_CONTEXTUAL_RESULT_SET: AgentErrorCode.AGENT_RUNTIME_ERROR,
    RuntimeNoticeCode.PREFER_ANALYSIS_CACHE_FILTER: AgentErrorCode.AGENT_RUNTIME_ERROR,
    RuntimeNoticeCode.PREFER_BATCH_ANALYSIS_TOOL: AgentErrorCode.AGENT_RUNTIME_ERROR,
}


def make_agent_error_payload(
    *,
    code: AgentErrorCode,
    message: str,
    stage: str,
    retryable: bool = False,
    status_code: int | None = None,
    provider: str | None = None,
    tool: str | None = None,
    details: Any = None,
    recommendations: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": code.value,
        "message": message,
        "stage": stage,
        "retryable": retryable,
        "severity": "error",
    }
    if status_code is not None:
        payload["status_code"] = status_code
    if provider:
        payload["provider"] = provider
    if tool:
        payload["tool"] = tool
    if details not in (None, "", {}):
        payload["details"] = details
    if recommendations:
        payload["recommendations"] = recommendations
    return payload
