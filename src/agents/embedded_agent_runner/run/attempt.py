"""jarvis.agents.embedded_agent_runner.run.attempt — top-level attempt runner.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.ts``.

Public surface:

- :func:`run_embedded_attempt` (async) — run one embedded attempt
  end-to-end (prompt dispatch, stream settlement, result
  projection, cleanup).

Phase 7.6d-3 — focused minimal port.

The OpenClaw source is the main entry point and tightly couples
every attempt subsystem (session lock, prompt phase, stream
settlement, cleanup, result projection, etc.). The Python port
keeps the public surface and delegates the heavy orchestration to
installable hooks so the host can plug in the real attempt
subsystems as they land.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded run attempt result.
EmbeddedRunAttemptResult = Dict[str, Any]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


async def _default_run_embedded_attempt_settled_phase(params: Dict[str, Any]) -> Any:
    from .attempt_execution_settle import run_embedded_attempt_settled_phase

    return await run_embedded_attempt_settled_phase(params)


#: Hook for the run-embedded-attempt-settled-phase step.
_RUN_EMBEDDED_ATTEMPT_SETTLED_PHASE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = _default_run_embedded_attempt_settled_phase


def set_run_embedded_attempt_settled_phase_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom runEmbeddedAttemptSettledPhase hook."""
    global _RUN_EMBEDDED_ATTEMPT_SETTLED_PHASE
    _RUN_EMBEDDED_ATTEMPT_SETTLED_PHASE = hook


async def _default_recover_embedded_run_attempt(params: Dict[str, Any]) -> Any:
    from .attempt_recovery import recover_embedded_run_attempt

    return await recover_embedded_run_attempt(params)


#: Hook for the recover-embedded-run-attempt step.
_RECOVER_EMBEDDED_RUN_ATTEMPT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = _default_recover_embedded_run_attempt


def set_recover_embedded_run_attempt_attempt_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom recoverEmbeddedRunAttempt hook."""
    global _RECOVER_EMBEDDED_RUN_ATTEMPT
    _RECOVER_EMBEDDED_RUN_ATTEMPT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_embedded_attempt(
    input_obj: Dict[str, Any],
) -> EmbeddedRunAttemptResult:
    """Run one embedded attempt end-to-end.

    Mirrors :func:`runEmbeddedAttempt` (``attempt.ts``).
    """
    result: Any = await _maybe_await(
        _RUN_EMBEDDED_ATTEMPT_SETTLED_PHASE(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    attempt = input_obj.get("attempt") or {}
    if result.get("promptError") or result.get("aborted") or result.get("timedOut"):
        recovery: Any = await _maybe_await(
            _RECOVER_EMBEDDED_RUN_ATTEMPT(
                {"attempt": attempt, "result": result, "input": input_obj}
            )
        )
        if isinstance(recovery, dict):
            result = {**result, **recovery}
    return result


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedRunAttemptResult",
    "run_embedded_attempt",
    "set_recover_embedded_run_attempt_attempt_hook",
    "set_run_embedded_attempt_settled_phase_hook",
]
