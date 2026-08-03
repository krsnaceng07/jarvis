"""jarvis.agents.embedded_agent_runner.run.attempt_trajectory_flush_cleanup — flush the attempt trajectory recorder.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-trajectory-flush-cleanup.ts``.

Public surface:

- :func:`flush_embedded_attempt_trajectory_recorder` (async)

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded attempt trajectory flush shape.
EmbeddedAttemptTrajectoryFlush = Dict[str, Any]


#: Installable hook for the flush-trajectory-recorder step.
_FLUSH_EMBEDDED_ATTEMPT_TRAJECTORY_RECORDER: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_flush_embedded_attempt_trajectory_recorder_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom flushEmbeddedAttemptTrajectoryRecorder hook."""
    global _FLUSH_EMBEDDED_ATTEMPT_TRAJECTORY_RECORDER
    _FLUSH_EMBEDDED_ATTEMPT_TRAJECTORY_RECORDER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def flush_embedded_attempt_trajectory_recorder(
    params: Dict[str, Any],
) -> EmbeddedAttemptTrajectoryFlush:
    """Flush the attempt trajectory recorder.

    Mirrors :func:`flushEmbeddedAttemptTrajectoryRecorder`
    (``attempt-trajectory-flush-cleanup.ts``).
    """
    result: Any = await _maybe_await(
        _FLUSH_EMBEDDED_ATTEMPT_TRAJECTORY_RECORDER(dict(params or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "flushed": bool(result.get("flushed", True)),
        "discarded": bool(result.get("discarded", False)),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptTrajectoryFlush",
    "flush_embedded_attempt_trajectory_recorder",
    "set_flush_embedded_attempt_trajectory_recorder_hook",
]
