"""jarvis.agents.embedded_agent_runner.run.attempt_execution_settle — run prompt dispatch, stream settlement, cleanup, and result projection.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-execution-settle.ts``.

Public surface:

- :func:`run_embedded_attempt_settled_phase` — run prompt dispatch,
  stream settlement, cleanup, and result projection for one attempt.

Phase 7.6b-2 — focused minimal port.

The OpenClaw source is tightly coupled to the prompt-phase, stream
finalize, session-spawn, usage-accumulator, abortable, and
diagnostic-trace-context layers. The Python port keeps the public
surface and delegates the heavy work to installable hooks so the
host can plug in the real layers as they land.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Attempt execution-phase input. Mirrors
#: :class:`EmbeddedAttemptExecutionPhaseInput` from
#: ``attempt-execution-types.ts``.
EmbeddedAttemptExecutionPhaseInput = Dict[str, Any]


#: Attempt execution state. Mirrors
#: :class:`EmbeddedAttemptExecutionState` from
#: ``attempt-execution-types.ts``.
EmbeddedAttemptExecutionState = Dict[str, Any]


#: Prepared stream runtime.
PreparedStreamRuntime = Dict[str, Any]


#: Final attempt result.
EmbeddedRunAttemptResult = Dict[str, Any]


# ---------------------------------------------------------------------------
# Installable hooks
# ---------------------------------------------------------------------------


async def _default_run_embedded_attempt_prompt_phase(params: Dict[str, Any]) -> Any:
    from .attempt_prompt_phase import run_embedded_attempt_prompt_phase

    return await run_embedded_attempt_prompt_phase(params)


#: Hook for :func:`runEmbeddedAttemptPromptPhase` from
#: ``attempt-prompt-phase.ts``.
_RUN_EMBEDDED_ATTEMPT_PROMPT_PHASE: Callable[[Dict[str, Any]], Awaitable[Any]] = (
    _default_run_embedded_attempt_prompt_phase
)


def set_run_embedded_attempt_prompt_phase_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom runEmbeddedAttemptPromptPhase hook."""
    global _RUN_EMBEDDED_ATTEMPT_PROMPT_PHASE
    _RUN_EMBEDDED_ATTEMPT_PROMPT_PHASE = hook


async def _default_finalize_embedded_attempt_stream_phase(params: Dict[str, Any]) -> Any:
    from .attempt_stream_finalize import finalize_embedded_attempt_stream_phase

    return await finalize_embedded_attempt_stream_phase(params)


#: Hook for :func:`finalizeEmbeddedAttemptStreamPhase` from
#: ``attempt-stream-finalize.ts``.
_FINALIZE_EMBEDDED_ATTEMPT_STREAM_PHASE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = _default_finalize_embedded_attempt_stream_phase


def set_finalize_embedded_attempt_stream_phase_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom finalizeEmbeddedAttemptStreamPhase hook."""
    global _FINALIZE_EMBEDDED_ATTEMPT_STREAM_PHASE
    _FINALIZE_EMBEDDED_ATTEMPT_STREAM_PHASE = hook


#: Hook for the cleanup-stream-execution step.
_CLEANUP_EMBEDDED_ATTEMPT_STREAM_EXECUTION: Callable[[Dict[str, Any]], None] = (
    lambda _params: None
)


def set_cleanup_embedded_attempt_stream_execution_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom cleanupEmbeddedAttemptStreamExecution hook."""
    global _CLEANUP_EMBEDDED_ATTEMPT_STREAM_EXECUTION
    _CLEANUP_EMBEDDED_ATTEMPT_STREAM_EXECUTION = hook


#: Hook for the subagent-spawn settle step.
_SETTLE_REQUESTER_AFTER_SESSION_SPAWNS: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _params: asyncio.sleep(0)


def set_settle_requester_after_session_spawns_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom settleRequesterAfterSessionSpawns hook."""
    global _SETTLE_REQUESTER_AFTER_SESSION_SPAWNS
    _SETTLE_REQUESTER_AFTER_SESSION_SPAWNS = hook


#: Hook for the clear-active-embedded-run step.
_CLEAR_ACTIVE_EMBEDDED_RUN: Callable[[Dict[str, Any]], None] = lambda _params: None


def set_clear_active_embedded_run_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom clearActiveEmbeddedRun hook."""
    global _CLEAR_ACTIVE_EMBEDDED_RUN
    _CLEAR_ACTIVE_EMBEDDED_RUN = hook


#: Hook for the detach-backend step.
_DETACH_BACKEND: Callable[[Dict[str, Any]], None] = lambda _params: None


def set_detach_backend_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom detachBackend hook."""
    global _DETACH_BACKEND
    _DETACH_BACKEND = hook


#: Hook for the remove-attempt-abort-signal-listener step.
_REMOVE_ATTEMPT_ABORT_SIGNAL_LISTENER: Callable[[Dict[str, Any]], None] = (
    lambda _params: None
)


def set_remove_attempt_abort_signal_listener_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom removeAttemptAbortSignalListener hook."""
    global _REMOVE_ATTEMPT_ABORT_SIGNAL_LISTENER
    _REMOVE_ATTEMPT_ABORT_SIGNAL_LISTENER = hook


#: Hook for the unsubscribe step.
_UNSUBSCRIBE: Callable[[Dict[str, Any]], None] = lambda _params: None


def set_unsubscribe_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom unsubscribe hook."""
    global _UNSUBSCRIBE
    _UNSUBSCRIBE = hook


#: Hook for the clear-attempt-timeout-timers step.
_CLEAR_ATTEMPT_TIMEOUT_TIMERS: Callable[[Dict[str, Any]], None] = lambda _params: None


def set_clear_attempt_timeout_timers_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom clearAttemptTimeoutTimers hook."""
    global _CLEAR_ATTEMPT_TIMEOUT_TIMERS
    _CLEAR_ATTEMPT_TIMEOUT_TIMERS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_embedded_attempt_settled_phase(
    input_obj: EmbeddedAttemptExecutionPhaseInput,
) -> EmbeddedRunAttemptResult:
    """Run prompt dispatch + stream settlement + cleanup + result projection.

    Mirrors :func:`runEmbeddedAttemptSettledPhase`
    (``attempt-execution-settle.ts:61-...``).
    """
    attempt = input_obj.get("attempt") or {}
    state = input_obj.get("state") or {}
    prepared_stream_runtime = input_obj.get("preparedStreamRuntime") or {}

    prompt_result: Any = await _maybe_await(
        _RUN_EMBEDDED_ATTEMPT_PROMPT_PHASE(
            {
                "attempt": attempt,
                "state": state,
                "preparedStreamRuntime": prepared_stream_runtime,
                "input": input_obj,
            }
        )
    )
    if prompt_result is not None and isinstance(prompt_result, dict):
        for key, value in prompt_result.items():
            state[key] = value

    settled_stream: Any = await _maybe_await(
        _FINALIZE_EMBEDDED_ATTEMPT_STREAM_PHASE(
            {
                "attempt": attempt,
                "state": state,
                "preparedStreamRuntime": prepared_stream_runtime,
                "input": input_obj,
            }
        )
    )
    if settled_stream is not None and isinstance(settled_stream, dict):
        for key, value in settled_stream.items():
            state[key] = value

    _CLEANUP_EMBEDDED_ATTEMPT_STREAM_EXECUTION(
        {
            "attempt": attempt,
            "state": state,
            "preparedStreamRuntime": prepared_stream_runtime,
        }
    )

    return {
        "runId": attempt.get("runId"),
        "sessionId": attempt.get("sessionId"),
        "sessionKey": attempt.get("sessionKey"),
        "sessionFile": attempt.get("sessionFile"),
        "agentId": attempt.get("agentId"),
        "aborted": bool(state.get("aborted")),
        "externalAbort": bool(state.get("externalAbort")),
        "timedOut": bool(state.get("timedOut")),
        "idleTimedOut": bool(state.get("idleTimedOut")),
        "timedOutDuringCompaction": bool(state.get("timedOutDuringCompaction")),
        "promptError": state.get("promptError"),
        "promptErrorSource": state.get("promptErrorSource"),
        "lastAssistant": state.get("lastAssistant"),
        "currentAttemptAssistant": state.get("currentAttemptAssistant"),
        "currentAttemptCompletedAssistant": state.get(
            "currentAttemptCompletedAssistant"
        ),
        "messagesSnapshot": state.get("messagesSnapshot") or [],
        "finalPromptText": state.get("finalPromptText"),
        "attemptUsage": state.get("attemptUsage"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptExecutionPhaseInput",
    "EmbeddedAttemptExecutionState",
    "EmbeddedRunAttemptResult",
    "PreparedStreamRuntime",
    "run_embedded_attempt_settled_phase",
    "set_clear_active_embedded_run_hook",
    "set_clear_attempt_timeout_timers_hook",
    "set_cleanup_embedded_attempt_stream_execution_hook",
    "set_detach_backend_hook",
    "set_finalize_embedded_attempt_stream_phase_hook",
    "set_remove_attempt_abort_signal_listener_hook",
    "set_run_embedded_attempt_prompt_phase_hook",
    "set_settle_requester_after_session_spawns_hook",
    "set_unsubscribe_hook",
]
