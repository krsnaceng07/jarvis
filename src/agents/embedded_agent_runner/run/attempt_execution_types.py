"""jarvis.agents.embedded_agent_runner.run.attempt_execution_types — execution-types for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-execution-types.ts``.

Public surface:

Types:

- :data:`EmbeddedAttemptExecutionState`
- :data:`EmbeddedAttemptExecutionPhaseInput`

Phase 7.6e — focused minimal port.

These are pure data types. The Python port keeps the public
surface and re-exports them as dict aliases.
"""
from __future__ import annotations

from typing import Any, Dict


#: Embedded attempt execution state. Mirrors
#: :class:`EmbeddedAttemptExecutionState`
#: (``attempt-execution-types.ts``).
EmbeddedAttemptExecutionState = Dict[str, Any]


#: Embedded attempt execution phase input. Mirrors
#: :class:`EmbeddedAttemptExecutionPhaseInput`
#: (``attempt-execution-types.ts``).
EmbeddedAttemptExecutionPhaseInput = Dict[str, Any]


__all__ = [
    "EmbeddedAttemptExecutionPhaseInput",
    "EmbeddedAttemptExecutionState",
]
