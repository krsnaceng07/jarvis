"""jarvis.agents.embedded_agent_runner.run.attempt_session — prepare the agent session for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-session.ts``.

Public surface:

- :func:`prepare_embedded_attempt_agent_session` (async)

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the prepare-embedded-attempt-agent-session step.
_PREPARE_EMBEDDED_ATTEMPT_AGENT_SESSION: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_embedded_attempt_agent_session_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepareEmbeddedAttemptAgentSession hook."""
    global _PREPARE_EMBEDDED_ATTEMPT_AGENT_SESSION
    _PREPARE_EMBEDDED_ATTEMPT_AGENT_SESSION = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_agent_session(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Prepare the agent session for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptAgentSession`
    (``attempt-session.ts``).
    """
    result: Any = await _maybe_await(
        _PREPARE_EMBEDDED_ATTEMPT_AGENT_SESSION(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "agentSession": result.get("agentSession"),
        "sessionId": result.get("sessionId"),
        "sessionFile": result.get("sessionFile"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "prepare_embedded_attempt_agent_session",
    "set_prepare_embedded_attempt_agent_session_hook",
]
