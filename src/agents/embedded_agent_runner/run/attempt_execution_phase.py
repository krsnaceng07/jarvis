"""jarvis.agents.embedded_agent_runner.run.attempt_execution_phase — run the execution phase of an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-execution-phase.ts``.

Public surface:

- :func:`run_embedded_attempt_execution_phase` (async)

Phase 7.6d-6 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt execution-phase shape.
EmbeddedAttemptExecutionPhase = Dict[str, Any]


#: Installable hook for the run-execution-phase step.
_RUN_EXECUTION_PHASE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_run_execution_phase_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom run-execution-phase hook."""
    global _RUN_EXECUTION_PHASE
    _RUN_EXECUTION_PHASE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_embedded_attempt_execution_phase(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptExecutionPhase:
    """Run the execution phase of an attempt.

    Mirrors :func:`runEmbeddedAttemptExecutionPhase`
    (``attempt-execution-phase.ts``).
    """
    result: Any = await _maybe_await(
        _RUN_EXECUTION_PHASE(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "outcome": result.get("outcome", "completed"),
        "attemptResult": result.get("attemptResult"),
        "execution": result.get("execution") or {},
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptExecutionPhase",
    "run_embedded_attempt_execution_phase",
    "set_run_execution_phase_hook",
]
