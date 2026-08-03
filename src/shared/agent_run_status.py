"""jarvis.shared.agent_run_status — agent-run status predicates.

OpenClaw parity: mirrors ``openclaw-main/src/shared/agent-run-status.ts``.
"""
from __future__ import annotations

#: Statuses that are not final and should keep waiters/subscribers attached.
_NON_TERMINAL_AGENT_RUN_STATUSES = frozenset({"accepted", "started", "in_flight"})


def is_non_terminal_agent_run_status(status: object) -> bool:
    """Return True for agent-run statuses that still need polling or live updates.

    Mirrors :func:`isNonTerminalAgentRunStatus`
    (``shared/agent-run-status.ts``).
    """
    return isinstance(status, str) and status in _NON_TERMINAL_AGENT_RUN_STATUSES


__all__ = ["is_non_terminal_agent_run_status"]
