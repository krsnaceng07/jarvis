"""jarvis.agents.embedded_agent_runner.run.blocked_run_result — build a blocked-run result.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/blocked-run-result.ts``.

Public surface:

- :func:`build_embedded_run_blocked_result`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Blocked-run result shape.
BlockedRunResult = Dict[str, Any]


#: Installable hook for the build-embedded-run-blocked-result step.
_BUILD_EMBEDDED_RUN_BLOCKED_RESULT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_embedded_run_blocked_result_blocked_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildEmbeddedRunBlockedResult hook."""
    global _BUILD_EMBEDDED_RUN_BLOCKED_RESULT
    _BUILD_EMBEDDED_RUN_BLOCKED_RESULT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_embedded_run_blocked_result(
    params: Dict[str, Any],
) -> BlockedRunResult:
    """Build the embedded-run blocked result.

    Mirrors :func:`buildEmbeddedRunBlockedResult`
    (``blocked-run-result.ts``).
    """
    result = _BUILD_EMBEDDED_RUN_BLOCKED_RESULT(dict(params or {}))
    if not isinstance(result, dict):
        result = {}
    return {
        "blocked": bool(result.get("blocked", True)),
        "blockedBy": result.get("blockedBy"),
        "message": result.get("message"),
    }


__all__ = [
    "BlockedRunResult",
    "build_embedded_run_blocked_result",
    "set_build_embedded_run_blocked_result_blocked_hook",
]
