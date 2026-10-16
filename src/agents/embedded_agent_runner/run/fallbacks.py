"""jarvis.agents.embedded_agent_runner.run.fallbacks — embedded-run fallback helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/fallbacks.ts``.

Public surface:

- :func:`resolve_thinking_fallback`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Default fallback thinking level.
DEFAULT_FALLBACK_THINKING_LEVEL: str = "medium"


#: Installable hook for the resolve-thinking-fallback step.
_RESOLVE_THINKING_FALLBACK: Callable[
    [Dict[str, Any]], str
] = lambda _p: DEFAULT_FALLBACK_THINKING_LEVEL


def set_resolve_thinking_fallback_hook(
    hook: Callable[[Dict[str, Any]], str],
) -> None:
    """Install a custom resolveThinkingFallback hook."""
    global _RESOLVE_THINKING_FALLBACK
    _RESOLVE_THINKING_FALLBACK = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_thinking_fallback(params: Dict[str, Any]) -> str:
    """Resolve the thinking-level fallback.

    Mirrors :func:`resolveThinkingFallback` (``fallbacks.ts``).
    """
    return _RESOLVE_THINKING_FALLBACK(dict(params or {}))


__all__ = [
    "DEFAULT_FALLBACK_THINKING_LEVEL",
    "resolve_thinking_fallback",
    "set_resolve_thinking_fallback_hook",
]
