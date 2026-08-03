"""jarvis.agents.embedded_agent_runner.run.agent_end_context — build the embedded-agent end context.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/agent-end-context.ts``.

Public surface:

- :func:`build_embedded_agent_end_context`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-agent end context shape.
EmbeddedAgentEndContext = Dict[str, Any]


#: Installable hook for the build-embedded-agent-end-context step.
_BUILD_EMBEDDED_AGENT_END_CONTEXT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_embedded_agent_end_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildEmbeddedAgentEndContext hook."""
    global _BUILD_EMBEDDED_AGENT_END_CONTEXT
    _BUILD_EMBEDDED_AGENT_END_CONTEXT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_embedded_agent_end_context(
    params: Dict[str, Any],
) -> EmbeddedAgentEndContext:
    """Build the embedded-agent end context.

    Mirrors :func:`buildEmbeddedAgentEndContext`
    (``agent-end-context.ts``).
    """
    context = _BUILD_EMBEDDED_AGENT_END_CONTEXT(dict(params or {}))
    if not isinstance(context, dict):
        context = {}
    return {
        "ended": bool(context.get("ended", True)),
        "summary": context.get("summary"),
    }


__all__ = [
    "EmbeddedAgentEndContext",
    "build_embedded_agent_end_context",
    "set_build_embedded_agent_end_context_hook",
]
