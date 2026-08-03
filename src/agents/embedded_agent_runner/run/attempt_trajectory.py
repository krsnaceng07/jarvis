"""jarvis.agents.embedded_agent_runner.run.attempt_trajectory — prepare the attempt trajectory.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-trajectory.ts``.

Public surface:

- :func:`prepare_embedded_attempt_trajectory` (async)

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded attempt trajectory shape.
EmbeddedAttemptTrajectory = Dict[str, Any]


#: Installable hook for the prepare-trajectory step.
_PREPARE_TRAJECTORY: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_trajectory_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepareEmbeddedAttemptTrajectory hook."""
    global _PREPARE_TRAJECTORY
    _PREPARE_TRAJECTORY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_trajectory(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptTrajectory:
    """Prepare the attempt trajectory.

    Mirrors :func:`prepareEmbeddedAttemptTrajectory`
    (``attempt-trajectory.ts``).
    """
    trajectory: Any = await _maybe_await(
        _PREPARE_TRAJECTORY(dict(input_obj or {}))
    )
    if not isinstance(trajectory, dict):
        trajectory = {}
    return {
        "recorder": trajectory.get("recorder"),
        "trajectory": trajectory.get("trajectory") or {},
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptTrajectory",
    "prepare_embedded_attempt_trajectory",
    "set_prepare_trajectory_hook",
]
