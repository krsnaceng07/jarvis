"""jarvis.agents.embedded_agent_runner.run.terminal_timeout — resolve the embedded-run terminal timeout.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/terminal-timeout.ts``.

Public surface:

- :func:`resolve_embedded_run_terminal_timeout`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the resolve-embedded-run-terminal-timeout step.
_RESOLVE_EMBEDDED_RUN_TERMINAL_TIMEOUT: Callable[
    [Dict[str, Any]], int
] = lambda _p: 0


def set_resolve_embedded_run_terminal_timeout_hook(
    hook: Callable[[Dict[str, Any]], int],
) -> None:
    """Install a custom resolveEmbeddedRunTerminalTimeout hook."""
    global _RESOLVE_EMBEDDED_RUN_TERMINAL_TIMEOUT
    _RESOLVE_EMBEDDED_RUN_TERMINAL_TIMEOUT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_run_terminal_timeout(
    input_obj: Dict[str, Any],
) -> int:
    """Resolve the embedded-run terminal timeout in milliseconds.

    Mirrors :func:`resolveEmbeddedRunTerminalTimeout`
    (``terminal-timeout.ts``).
    """
    return int(
        _RESOLVE_EMBEDDED_RUN_TERMINAL_TIMEOUT(dict(input_obj or {}))
        or 0
    )


__all__ = [
    "resolve_embedded_run_terminal_timeout",
    "set_resolve_embedded_run_terminal_timeout_hook",
]
