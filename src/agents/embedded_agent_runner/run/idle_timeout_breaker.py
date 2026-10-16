"""jarvis.agents.embedded_agent_runner.run.idle_timeout_breaker — break the LLM stream on idle timeout.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/idle-timeout-breaker.ts``.

Public surface:

- :func:`should_break_on_idle_timeout`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the should-break-on-idle-timeout step.
_SHOULD_BREAK_ON_IDLE_TIMEOUT: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_break_on_idle_timeout_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldBreakOnIdleTimeout hook."""
    global _SHOULD_BREAK_ON_IDLE_TIMEOUT
    _SHOULD_BREAK_ON_IDLE_TIMEOUT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def should_break_on_idle_timeout(params: Dict[str, Any]) -> bool:
    """Return True when the idle-timeout should break the LLM stream.

    Mirrors :func:`shouldBreakOnIdleTimeout`
    (``idle-timeout-breaker.ts``).
    """
    return _SHOULD_BREAK_ON_IDLE_TIMEOUT(dict(params or {}))


__all__ = [
    "set_should_break_on_idle_timeout_hook",
    "should_break_on_idle_timeout",
]
