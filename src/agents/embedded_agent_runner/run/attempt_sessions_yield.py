"""jarvis.agents.embedded_agent_runner.run.attempt_sessions_yield — wait for sessions-yield abort settlement.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.sessions-yield.ts``.

Public surface:

Constants:

- :data:`SESSIONS_YIELD_ABORT_REASON`

Functions:

- :func:`wait_for_sessions_yield_abort_settle` (async)
- :func:`create_yield_aborted_response`
- :func:`is_sessions_yield_abort_error`
- :func:`is_sessions_yield_abort_reason`
- :func:`queue_sessions_yield_interrupt_message`
- :func:`persist_sessions_yield_context_message` (async)
- :func:`strip_sessions_yield_artifacts`

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Sessions-yield abort reason. Mirrors :data:`SESSIONS_YIELD_ABORT_REASON`
#: (``attempt.sessions-yield.ts``).
SESSIONS_YIELD_ABORT_REASON: Dict[str, Any] = {
    "code": "sessions_yield",
    "turnHandoff": True,
}


#: Installable hook for the wait-for-sessions-yield-abort-settle step.
_WAIT_FOR_SESSIONS_YIELD_ABORT_SETTLE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_wait_for_sessions_yield_abort_settle_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom waitForSessionsYieldAbortSettle hook."""
    global _WAIT_FOR_SESSIONS_YIELD_ABORT_SETTLE
    _WAIT_FOR_SESSIONS_YIELD_ABORT_SETTLE = hook


#: Installable hook for the create-yield-aborted-response step.
_CREATE_YIELD_ABORTED_RESPONSE: Callable[
    [Dict[str, Any]], Any
] = lambda p: {"aborted": True, "reason": dict(SESSIONS_YIELD_ABORT_REASON)}


def set_create_yield_aborted_response_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createYieldAbortedResponse hook."""
    global _CREATE_YIELD_ABORTED_RESPONSE
    _CREATE_YIELD_ABORTED_RESPONSE = hook


#: Installable hook for the queue-sessions-yield-interrupt-message step.
_QUEUE_SESSIONS_YIELD_INTERRUPT_MESSAGE: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_queue_sessions_yield_interrupt_message_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom queueSessionsYieldInterruptMessage hook."""
    global _QUEUE_SESSIONS_YIELD_INTERRUPT_MESSAGE
    _QUEUE_SESSIONS_YIELD_INTERRUPT_MESSAGE = hook


#: Installable hook for the persist-sessions-yield-context-message step.
_PERSIST_SESSIONS_YIELD_CONTEXT_MESSAGE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_persist_sessions_yield_context_message_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom persistSessionsYieldContextMessage hook."""
    global _PERSIST_SESSIONS_YIELD_CONTEXT_MESSAGE
    _PERSIST_SESSIONS_YIELD_CONTEXT_MESSAGE = hook


#: Installable hook for the strip-sessions-yield-artifacts step.
_STRIP_SESSIONS_YIELD_ARTIFACTS: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_strip_sessions_yield_artifacts_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom stripSessionsYieldArtifacts hook."""
    global _STRIP_SESSIONS_YIELD_ARTIFACTS
    _STRIP_SESSIONS_YIELD_ARTIFACTS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def wait_for_sessions_yield_abort_settle(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Wait for sessions-yield abort settlement.

    Mirrors :func:`waitForSessionsYieldAbortSettle`
    (``attempt.sessions-yield.ts``).
    """
    result: Any = await _maybe_await(
        _WAIT_FOR_SESSIONS_YIELD_ABORT_SETTLE(dict(params or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "settled": bool(result.get("settled", True)),
        "sessionId": result.get("sessionId"),
    }


def create_yield_aborted_response(
    model: Dict[str, Any],
) -> Dict[str, Any]:
    """Create a yield-aborted response.

    Mirrors :func:`createYieldAbortedResponse`
    (``attempt.sessions-yield.ts``).
    """
    return _CREATE_YIELD_ABORTED_RESPONSE(dict(model or {}))


def is_sessions_yield_abort_error(err: Any) -> bool:
    """Return True when ``err`` carries the sessions-yield abort reason.

    Mirrors :func:`isSessionsYieldAbortError`
    (``attempt.sessions-yield.ts``).
    """
    if not isinstance(err, dict):
        return False
    reason = err.get("reason")
    if isinstance(reason, dict) and reason.get("code") == "sessions_yield":
        return True
    return err.get("code") == "sessions_yield"


def is_sessions_yield_abort_reason(reason: Any) -> bool:
    """Return True when ``reason`` is the sessions-yield abort reason.

    Mirrors :func:`isSessionsYieldAbortReason`
    (``attempt.sessions-yield.ts``).
    """
    if isinstance(reason, dict):
        return reason.get("code") == "sessions_yield"
    return reason == "sessions_yield"


def queue_sessions_yield_interrupt_message(
    active_session: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Queue the sessions-yield interrupt message.

    Mirrors :func:`queueSessionsYieldInterruptMessage`
    (``attempt.sessions-yield.ts``).
    """
    return _QUEUE_SESSIONS_YIELD_INTERRUPT_MESSAGE({"activeSession": active_session})


async def persist_sessions_yield_context_message(
    active_session: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Persist the sessions-yield context message.

    Mirrors :func:`persistSessionsYieldContextMessage`
    (``attempt.sessions-yield.ts``).
    """
    return await _maybe_await(
        _PERSIST_SESSIONS_YIELD_CONTEXT_MESSAGE(
            {"activeSession": active_session}
        )
    )


def strip_sessions_yield_artifacts(
    active_session: Dict[str, Any],
) -> None:
    """Strip the sessions-yield artifacts from the active session.

    Mirrors :func:`stripSessionsYieldArtifacts`
    (``attempt.sessions-yield.ts``).
    """
    _STRIP_SESSIONS_YIELD_ARTIFACTS({"activeSession": active_session})


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "SESSIONS_YIELD_ABORT_REASON",
    "create_yield_aborted_response",
    "is_sessions_yield_abort_error",
    "is_sessions_yield_abort_reason",
    "persist_sessions_yield_context_message",
    "queue_sessions_yield_interrupt_message",
    "set_create_yield_aborted_response_hook",
    "set_persist_sessions_yield_context_message_hook",
    "set_queue_sessions_yield_interrupt_message_hook",
    "set_strip_sessions_yield_artifacts_hook",
    "set_wait_for_sessions_yield_abort_settle_hook",
    "strip_sessions_yield_artifacts",
    "wait_for_sessions_yield_abort_settle",
]
