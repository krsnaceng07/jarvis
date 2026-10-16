"""jarvis.agents.embedded_agent_runner.run.attempt_stream_finalize — finalize the attempt stream phase.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-stream-finalize.ts``.

Public surface:

- :func:`finalize_embedded_attempt_stream_phase` (async)

Phase 7.6d-5 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt stream-finalize shape.
EmbeddedAttemptStreamFinalize = Dict[str, Any]


#: Installable hook for the finalize-attempt-stream-phase step.
_FINALIZE_ATTEMPT_STREAM_PHASE: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_finalize_attempt_stream_phase_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom finalize-attempt-stream-phase hook."""
    global _FINALIZE_ATTEMPT_STREAM_PHASE
    _FINALIZE_ATTEMPT_STREAM_PHASE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def finalize_embedded_attempt_stream_phase(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptStreamFinalize:
    """Finalize the attempt stream phase.

    Mirrors :func:`finalizeEmbeddedAttemptStreamPhase`
    (``attempt-stream-finalize.ts``).
    """
    finalized: Any = await _maybe_await(
        _FINALIZE_ATTEMPT_STREAM_PHASE(dict(input_obj or {}))
    )
    if not isinstance(finalized, dict):
        finalized = {}
    return {
        "stream": finalized.get("stream"),
        "messagesSnapshot": finalized.get("messagesSnapshot") or [],
        "lastAssistant": finalized.get("lastAssistant"),
        "currentAttemptAssistant": finalized.get("currentAttemptAssistant"),
        "currentAttemptCompletedAssistant": finalized.get(
            "currentAttemptCompletedAssistant"
        ),
        "attemptUsage": finalized.get("attemptUsage"),
        "cacheBreak": finalized.get("cacheBreak"),
        "promptCache": finalized.get("promptCache"),
        "timedOutDuringCompaction": bool(
            finalized.get("timedOutDuringCompaction", False)
        ),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptStreamFinalize",
    "finalize_embedded_attempt_stream_phase",
    "set_finalize_attempt_stream_phase_hook",
]
