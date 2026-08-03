"""jarvis.agents.embedded_agent_runner.run.runtime_resolution — resolve the runtime-model + think-level for a run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/runtime-resolution.ts``.

Public surface:

- :func:`resolve_initial_think_level`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the resolve-initial-think-level step.
_RESOLVE_INITIAL_THINK_LEVEL: Callable[
    [Dict[str, Any]], str
] = lambda _p: "medium"


def set_resolve_initial_think_level_runtime_resolution_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom resolveInitialThinkLevel hook."""
    global _RESOLVE_INITIAL_THINK_LEVEL
    _RESOLVE_INITIAL_THINK_LEVEL = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_initial_think_level(params: Dict[str, Any]) -> str:
    """Resolve the initial think-level for a run.

    Mirrors :func:`resolveInitialThinkLevel`
    (``runtime-resolution.ts``).
    """
    return _RESOLVE_INITIAL_THINK_LEVEL(dict(params or {}))


__all__ = [
    "resolve_initial_think_level",
    "set_resolve_initial_think_level_runtime_resolution_hook",
]
