"""jarvis.agents.embedded_agent_runner.run.attempt_queue_message — steer an active session with optional delivery wait.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.queue-message.ts``.

Public surface:

- :func:`steer_active_session_with_optional_delivery_wait` (async)

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Steer outcome.
SteerOutcome = Dict[str, Any]


#: Installable hook for the steer-active-session-with-optional-delivery-wait step.
_STEER_ACTIVE_SESSION_WITH_OPTIONAL_DELIVERY_WAIT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_steer_active_session_with_optional_delivery_wait_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom steerActiveSessionWithOptionalDeliveryWait hook."""
    global _STEER_ACTIVE_SESSION_WITH_OPTIONAL_DELIVERY_WAIT
    _STEER_ACTIVE_SESSION_WITH_OPTIONAL_DELIVERY_WAIT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def steer_active_session_with_optional_delivery_wait(
    params: Dict[str, Any],
) -> SteerOutcome:
    """Steer an active session with optional delivery wait.

    Mirrors :func:`steerActiveSessionWithOptionalDeliveryWait`
    (``attempt.queue-message.ts``).
    """
    result: Any = await _maybe_await(
        _STEER_ACTIVE_SESSION_WITH_OPTIONAL_DELIVERY_WAIT(
            dict(params or {})
        )
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "steered": bool(result.get("steered", True)),
        "delivered": bool(result.get("delivered", False)),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "SteerOutcome",
    "set_steer_active_session_with_optional_delivery_wait_hook",
    "steer_active_session_with_optional_delivery_wait",
]
