"""jarvis.agents.embedded_agent_runner.run.context_recovery_state — embedded-run context-recovery state shape.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/context-recovery-state.ts``.

Public surface:

Types:

- :data:`EmbeddedRunContextRecoveryState`
- :func:`create_embedded_run_context_recovery_state`
"""
from __future__ import annotations

from typing import Any, Dict, Optional


#: Embedded-run context-recovery state shape. Mirrors
#: :class:`EmbeddedRunContextRecoveryState`
#: (``context-recovery-state.ts``).
EmbeddedRunContextRecoveryState = Dict[str, Any]


def create_embedded_run_context_recovery_state() -> Dict[str, Any]:
    """Create fresh context recovery state for an embedded run."""
    state: Dict[str, Any] = {
        "autoCompactionCount": 0,
        "compactionRequestBudget": None,
        "lastCompactionTokensAfter": None,
        "currentContextSnapshot": None,
        "lastContextBudgetStatus": None,
        "overflowCompactionAttempts": 0,
        "timeoutCompactionAttempts": 0,
        "toolResultTruncationAttempted": False,
    }
    return state


__all__ = [
    "EmbeddedRunContextRecoveryState",
    "create_embedded_run_context_recovery_state",
]
