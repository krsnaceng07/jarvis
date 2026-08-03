"""jarvis.agents.embedded_agent_runner.run.attempt_tool_search_run_plan — resolve the tool-search run plan for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.tool-search-run-plan.ts``.

Public surface:

- :func:`resolve_attempt_tool_search_run_plan`

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Tool-search run plan shape.
AttemptToolSearchRunPlan = Dict[str, Any]


#: Installable hook for the resolve-tool-search-run-plan step.
_RESOLVE_TOOL_SEARCH_RUN_PLAN: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_resolve_tool_search_run_plan_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolve-tool-search-run-plan hook."""
    global _RESOLVE_TOOL_SEARCH_RUN_PLAN
    _RESOLVE_TOOL_SEARCH_RUN_PLAN = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_attempt_tool_search_run_plan(
    params: Dict[str, Any],
) -> AttemptToolSearchRunPlan:
    """Resolve the tool-search run plan for an attempt.

    Mirrors :func:`resolveAttemptToolSearchRunPlan`
    (``attempt.tool-search-run-plan.ts``).
    """
    plan = _RESOLVE_TOOL_SEARCH_RUN_PLAN(dict(params or {}))
    if not isinstance(plan, dict):
        plan = {}
    return {
        "shouldRunToolSearch": bool(plan.get("shouldRunToolSearch", False)),
        "compacted": plan.get("compacted"),
    }


__all__ = [
    "AttemptToolSearchRunPlan",
    "resolve_attempt_tool_search_run_plan",
    "set_resolve_tool_search_run_plan_hook",
]
