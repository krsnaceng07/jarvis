"""jarvis.agents.embedded_agent_runner.run.turn_taint_state — Sticky current-turn taint.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/turn-taint-state.ts``.
"""

from __future__ import annotations

from typing import Any, Protocol


class AgentTurnTaintState(Protocol):
    def observe(self, observation: Any) -> None: ...
    def is_tainted(self) -> bool: ...


class _AgentTurnTaintStateImpl:
    def __init__(self, initially_tainted: bool = False) -> None:
        self._tainted = initially_tainted

    def observe(self, observation: Any) -> None:
        presentation_only = getattr(observation, "presentationOnly", False)
        if isinstance(observation, dict):
            presentation_only = observation.get("presentationOnly", False)
            source = observation.get("resultContentSource")
        else:
            source = getattr(observation, "resultContentSource", None)

        if not presentation_only and source == "network":
            self._tainted = True

    def is_tainted(self) -> bool:
        return self._tainted


def create_agent_turn_taint_state(initially_tainted: bool = False) -> _AgentTurnTaintStateImpl:
    return _AgentTurnTaintStateImpl(initially_tainted=initially_tainted)


__all__ = ["create_agent_turn_taint_state", "AgentTurnTaintState"]
