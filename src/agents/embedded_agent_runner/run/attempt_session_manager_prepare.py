"""jarvis.agents.embedded_agent_runner.run.attempt_session_manager_prepare — prepare the session manager for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-session-manager-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_session_manager` (async)

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt session-manager shape.
EmbeddedAttemptSessionManager = Dict[str, Any]


#: Installable hook for the prepare-session-manager step.
_PREPARE_SESSION_MANAGER: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_session_manager_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepare-session-manager hook."""
    global _PREPARE_SESSION_MANAGER
    _PREPARE_SESSION_MANAGER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_session_manager(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptSessionManager:
    """Prepare the session manager for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptSessionManager`
    (``attempt-session-manager-prepare.ts``).
    """
    manager: Any = await _maybe_await(
        _PREPARE_SESSION_MANAGER(dict(input_obj or {}))
    )
    if not isinstance(manager, dict):
        manager = {}
    return {
        "sessionManager": manager.get("sessionManager"),
        "sessionState": manager.get("sessionState") or {},
        "sessionFile": manager.get("sessionFile"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptSessionManager",
    "prepare_embedded_attempt_session_manager",
    "set_prepare_session_manager_hook",
]
