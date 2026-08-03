"""jarvis.agents.embedded_agent_runner.run.attempt_tool_run_context — build the tool-run context for one attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.tool-run-context.ts``.

Public surface:

- :func:`build_embedded_attempt_tool_run_context`

Phase 7.6d-1 — focused minimal port.

The OpenClaw source builds the per-attempt tool-run context that
the tool-execution layer reads. The Python port keeps the public
surface and delegates the heavy work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


#: Embedded-attempt tool-run context.
EmbeddedAttemptToolRunContext = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


#: Hook for the build-embedded-attempt-tool-run-context step.
_BUILD_EMBEDDED_ATTEMPT_TOOL_RUN_CONTEXT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_build_embedded_attempt_tool_run_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom build-embedded-attempt-tool-run-context hook."""
    global _BUILD_EMBEDDED_ATTEMPT_TOOL_RUN_CONTEXT
    _BUILD_EMBEDDED_ATTEMPT_TOOL_RUN_CONTEXT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_embedded_attempt_tool_run_context(
    params: Dict[str, Any],
) -> EmbeddedAttemptToolRunContext:
    """Build the tool-run context for one attempt.

    Mirrors :func:`buildEmbeddedAttemptToolRunContext`
    (``attempt.tool-run-context.ts``).
    """
    return {
        "attempt": params.get("attempt"),
        "agentSession": params.get("agentSession"),
        "tools": params.get("tools") or [],
        "toolContext": _BUILD_EMBEDDED_ATTEMPT_TOOL_RUN_CONTEXT(dict(params or {})),
    }


__all__ = [
    "EmbeddedAttemptToolRunContext",
    "build_embedded_attempt_tool_run_context",
    "set_build_embedded_attempt_tool_run_context_hook",
]
