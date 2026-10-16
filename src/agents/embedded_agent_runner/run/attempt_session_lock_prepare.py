"""jarvis.agents.embedded_agent_runner.run.attempt_session_lock_prepare — prepare the session lock for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-session-lock-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_session_lock` (async)

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Installable hook for the prepare-embedded-attempt-session-lock step.
_PREPARE_EMBEDDED_ATTEMPT_SESSION_LOCK: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_embedded_attempt_session_lock_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepareEmbeddedAttemptSessionLock hook."""
    global _PREPARE_EMBEDDED_ATTEMPT_SESSION_LOCK
    _PREPARE_EMBEDDED_ATTEMPT_SESSION_LOCK = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_session_lock(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Prepare the session lock for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptSessionLock`
    (``attempt-session-lock-prepare.ts``).
    """
    result: Any = await _maybe_await(
        _PREPARE_EMBEDDED_ATTEMPT_SESSION_LOCK(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "prepared": bool(result.get("prepared", True)),
        "sessionLockController": result.get("sessionLockController"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "prepare_embedded_attempt_session_lock",
    "set_prepare_embedded_attempt_session_lock_hook",
]
