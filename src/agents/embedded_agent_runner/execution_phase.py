"""jarvis.agents.embedded_agent_runner.execution_phase — execution phase labels.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/execution-phase.ts``.

Public surface (mirrors the OpenClaw
source):

- :data:`EMBEDDED_AGENT_EXECUTION_PHASES` —
  the ordered list of execution
  phases.
- :data:`EmbeddedAgentExecutionPhase` —
  the phase-id type.
- :data:`EMBEDDED_AGENT_EXECUTION_PHASE_LABELS` —
  the compact label map.
- :func:`format_embedded_agent_execution_phase` —
  convert an internal phase id into
  the compact label used in status
  output.

Phase 7.0 — focused minimal port.
"""
from __future__ import annotations

from typing import Optional


#: The ordered list of execution
#: milestones. Mirrors
#: :data:`EMBEDDED_AGENT_EXECUTION_PHASES`
#: (``execution-phase.ts:6-21``).
EMBEDDED_AGENT_EXECUTION_PHASES: tuple = (
    "runner_entered",
    "workspace",
    "runtime_plugins",
    "before_agent_reply",
    "model_resolution",
    "auth",
    "context_engine",
    "attempt_dispatch",
    "context_assembled",
    "turn_accepted",
    "process_spawned",
    "tool_execution_started",
    "assistant_output_started",
    "model_call_started",
)


#: The phase-id type. Mirrors
#: :data:`EmbeddedAgentExecutionPhase`
#: (``execution-phase.ts:23``).
EmbeddedAgentExecutionPhase = str


#: The compact label map. Mirrors
#: :data:`EMBEDDED_AGENT_EXECUTION_PHASE_LABELS`
#: (``execution-phase.ts:25-40``).
EMBEDDED_AGENT_EXECUTION_PHASE_LABELS: dict = {
    "runner_entered": "runner-entered",
    "workspace": "workspace",
    "runtime_plugins": "runtime-plugins",
    "before_agent_reply": "before-agent-reply",
    "model_resolution": "model-resolution",
    "auth": "auth",
    "context_engine": "context-engine",
    "attempt_dispatch": "attempt-dispatch",
    "context_assembled": "context-assembled",
    "turn_accepted": "turn-accepted",
    "process_spawned": "process-spawned",
    "tool_execution_started": "tool-execution-started",
    "assistant_output_started": "assistant-output-started",
    "model_call_started": "model-call-started",
}


def format_embedded_agent_execution_phase(
    phase: Optional[EmbeddedAgentExecutionPhase],
) -> Optional[str]:
    """Convert an internal phase id
    into the compact label. Mirrors
    :func:`formatEmbeddedAgentExecutionPhase`
    (``execution-phase.ts:43-47``)."""
    if not phase:
        return None
    return EMBEDDED_AGENT_EXECUTION_PHASE_LABELS.get(phase)


__all__ = [
    "EMBEDDED_AGENT_EXECUTION_PHASES",
    "EMBEDDED_AGENT_EXECUTION_PHASE_LABELS",
    "EmbeddedAgentExecutionPhase",
    "format_embedded_agent_execution_phase",
]
