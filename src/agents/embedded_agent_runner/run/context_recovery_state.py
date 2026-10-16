"""jarvis.agents.embedded_agent_runner.run.context_recovery_state — embedded-run context-recovery state shape.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/context-recovery-state.ts``.

Public surface:

Types:

- :data:`EmbeddedRunContextRecoveryState`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict


#: Embedded-run context-recovery state shape. Mirrors
#: :class:`EmbeddedRunContextRecoveryState`
#: (``context-recovery-state.ts``).
EmbeddedRunContextRecoveryState = Dict[str, Any]


__all__ = [
    "EmbeddedRunContextRecoveryState",
]
