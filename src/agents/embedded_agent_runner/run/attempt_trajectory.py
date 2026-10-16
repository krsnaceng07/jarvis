"""jarvis.agents.embedded_agent_runner.run.attempt_trajectory — prepare the attempt trajectory.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-trajectory.ts``.

Public surface:

- :func:`prepare_embedded_attempt_trajectory` (async)

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict

from src.trajectory.runtime import create_trajectory_runtime_recorder


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
    options = {}
    if input_obj.get("sessionFile"):
        options["storePath"] = input_obj["sessionFile"]
        options["sessionId"] = input_obj.get("sessionId", "")
        options["agentId"] = input_obj.get("agentId")
        options["runId"] = input_obj.get("runId")
        options["workspaceDir"] = input_obj.get("workspaceDir")
        options["env"] = input_obj.get("env")

    recorder = create_trajectory_runtime_recorder(options) if options.get("storePath") else None

    # Hook support
    trajectory: Any = await _maybe_await(
        _PREPARE_TRAJECTORY(dict(input_obj or {}))
    )
    if not isinstance(trajectory, dict):
        trajectory = {}
        
    return {
        "recorder": recorder or trajectory.get("recorder"),
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
