"""jarvis.agents.embedded_agent_runner.run.attempt_after_turn — complete the after-turn phase of an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-after-turn.ts``.

Public surface:

- :func:`complete_embedded_attempt_after_turn` (async)

Phase 7.6h-1 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the complete-embedded-attempt-after-turn step.
_COMPLETE_EMBEDDED_ATTEMPT_AFTER_TURN: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_complete_embedded_attempt_after_turn_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom completeEmbeddedAttemptAfterTurn hook."""
    global _COMPLETE_EMBEDDED_ATTEMPT_AFTER_TURN
    _COMPLETE_EMBEDDED_ATTEMPT_AFTER_TURN = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def complete_embedded_attempt_after_turn(
    input_obj: Dict[str, Any],
) -> Dict[str, Any]:
    """Complete the after-turn phase of an attempt.

    Mirrors :func:`completeEmbeddedAttemptAfterTurn`
    (``attempt-after-turn.ts``).
    """
    result: Any = await _maybe_await(
        _COMPLETE_EMBEDDED_ATTEMPT_AFTER_TURN(dict(input_obj or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "completed": bool(result.get("completed", True)),
        "result": result.get("result"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "complete_embedded_attempt_after_turn",
    "set_complete_embedded_attempt_after_turn_hook",
]
