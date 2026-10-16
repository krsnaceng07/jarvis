"""jarvis.agents.embedded_agent_runner.run.attempt_session_cleanup — cleanup the session phase of an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-session-cleanup.ts``.

Public surface:

- :func:`cleanup_embedded_attempt_session_phase` (async)

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Installable hook for the cleanup-embedded-attempt-session-phase step.
_CLEANUP_EMBEDDED_ATTEMPT_SESSION_PHASE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_cleanup_embedded_attempt_session_phase_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom cleanupEmbeddedAttemptSessionPhase hook."""
    global _CLEANUP_EMBEDDED_ATTEMPT_SESSION_PHASE
    _CLEANUP_EMBEDDED_ATTEMPT_SESSION_PHASE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def cleanup_embedded_attempt_session_phase(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Cleanup the session phase of an attempt.

    Mirrors :func:`cleanupEmbeddedAttemptSessionPhase`
    (``attempt-session-cleanup.ts``).
    """
    result: Any = await _maybe_await(
        _CLEANUP_EMBEDDED_ATTEMPT_SESSION_PHASE(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "cleanedUp": bool(result.get("cleanedUp", True)),
        "result": result.get("result"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "cleanup_embedded_attempt_session_phase",
    "set_cleanup_embedded_attempt_session_phase_hook",
]
