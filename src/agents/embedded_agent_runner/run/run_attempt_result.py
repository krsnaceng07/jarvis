"""jarvis.agents.embedded_agent_runner.run.run_attempt_result — normalize and summarize the embedded-run attempt result.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/run-attempt-result.ts``.

Public surface:

Functions:

- :func:`normalize_embedded_run_attempt_result`
- :func:`has_completed_model_progress_for_idle_breaker`
- :func:`build_trace_tool_summary`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the normalize-embedded-run-attempt-result step.
_NORMALIZE_EMBEDDED_RUN_ATTEMPT_RESULT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_normalize_embedded_run_attempt_result_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom normalizeEmbeddedRunAttemptResult hook."""
    global _NORMALIZE_EMBEDDED_RUN_ATTEMPT_RESULT
    _NORMALIZE_EMBEDDED_RUN_ATTEMPT_RESULT = hook


#: Installable hook for the has-completed-model-progress-for-idle-breaker step.
_HAS_COMPLETED_MODEL_PROGRESS_FOR_IDLE_BREAKER: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_has_completed_model_progress_for_idle_breaker_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom hasCompletedModelProgressForIdleBreaker hook."""
    global _HAS_COMPLETED_MODEL_PROGRESS_FOR_IDLE_BREAKER
    _HAS_COMPLETED_MODEL_PROGRESS_FOR_IDLE_BREAKER = hook


#: Installable hook for the build-trace-tool-summary step.
_BUILD_TRACE_TOOL_SUMMARY: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_trace_tool_summary_run_attempt_result_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildTraceToolSummary hook."""
    global _BUILD_TRACE_TOOL_SUMMARY
    _BUILD_TRACE_TOOL_SUMMARY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_embedded_run_attempt_result(
    params: Dict[str, Any],
) -> Any:
    """Normalize the embedded-run attempt result.

    Mirrors :func:`normalizeEmbeddedRunAttemptResult`
    (``run-attempt-result.ts``).
    """
    return _NORMALIZE_EMBEDDED_RUN_ATTEMPT_RESULT(dict(params or {}))


def has_completed_model_progress_for_idle_breaker(
    params: Dict[str, Any],
) -> bool:
    """Return True when the model made progress for the idle-breaker.

    Mirrors :func:`hasCompletedModelProgressForIdleBreaker`
    (``run-attempt-result.ts``).
    """
    return _HAS_COMPLETED_MODEL_PROGRESS_FOR_IDLE_BREAKER(
        dict(params or {})
    )


def build_trace_tool_summary(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the trace tool summary.

    Mirrors :func:`buildTraceToolSummary`
    (``run-attempt-result.ts``).
    """
    return _BUILD_TRACE_TOOL_SUMMARY(dict(params or {}))


__all__ = [
    "build_trace_tool_summary",
    "has_completed_model_progress_for_idle_breaker",
    "normalize_embedded_run_attempt_result",
    "set_build_trace_tool_summary_run_attempt_result_hook",
    "set_has_completed_model_progress_for_idle_breaker_hook",
    "set_normalize_embedded_run_attempt_result_hook",
]
