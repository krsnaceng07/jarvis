"""jarvis.agents.embedded_agent_runner.run.terminal_retry_state — track the terminal-retry state for an embedded run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/terminal-retry-state.ts``.

Public surface:

- :func:`get_terminal_retry_state`
- :func:`increment_terminal_retry`
- :func:`reset_terminal_retry_state`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Per-run terminal-retry counter.
_TERMINAL_RETRY_COUNTER: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_terminal_retry_state(run_id: Optional[str]) -> Dict[str, Any]:
    """Get the terminal-retry state for a run.

    Mirrors :func:`getTerminalRetryState`
    (``terminal-retry-state.ts``).
    """
    if not run_id:
        return {"retries": 0}
    return {"retries": _TERMINAL_RETRY_COUNTER.get(run_id, 0)}


def increment_terminal_retry(run_id: Optional[str]) -> int:
    """Increment the terminal-retry counter for a run.

    Mirrors :func:`incrementTerminalRetry`
    (``terminal-retry-state.ts``).
    """
    if not run_id:
        return 0
    _TERMINAL_RETRY_COUNTER[run_id] = (
        _TERMINAL_RETRY_COUNTER.get(run_id, 0) + 1
    )
    return _TERMINAL_RETRY_COUNTER[run_id]


def reset_terminal_retry_state(run_id: Optional[str]) -> None:
    """Reset the terminal-retry state for a run.

    Mirrors :func:`resetTerminalRetryState`
    (``terminal-retry-state.ts``).
    """
    if not run_id:
        return
    _TERMINAL_RETRY_COUNTER.pop(run_id, None)


__all__ = [
    "get_terminal_retry_state",
    "increment_terminal_retry",
    "reset_terminal_retry_state",
]
