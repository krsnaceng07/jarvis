"""jarvis.agents.embedded_agent_runner.run.lane_controller — create the embedded-run lane controller.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/lane-controller.ts``.

Public surface:

- :func:`create_embedded_run_lane_controller`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, TypeVar


TParams = TypeVar("TParams", bound=Dict[str, Any])


#: Lane params type.
LaneParams = Dict[str, Any]


#: Embedded-run lane controller shape.
EmbeddedRunLaneController = Dict[str, Any]


#: Installable hook for the create-embedded-run-lane-controller step.
_CREATE_EMBEDDED_RUN_LANE_CONTROLLER: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_create_embedded_run_lane_controller_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom createEmbeddedRunLaneController hook."""
    global _CREATE_EMBEDDED_RUN_LANE_CONTROLLER
    _CREATE_EMBEDDED_RUN_LANE_CONTROLLER = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def create_embedded_run_lane_controller(
    options: Dict[str, Any],
) -> EmbeddedRunLaneController:
    """Create the embedded-run lane controller.

    Mirrors :func:`createEmbeddedRunLaneController`
    (``lane-controller.ts``).
    """
    controller = _CREATE_EMBEDDED_RUN_LANE_CONTROLLER(
        dict(options or {})
    )
    if not isinstance(controller, dict):
        controller = {}
    return {
        "lane": controller.get("lane") or "main",
        "controller": controller.get("controller"),
    }


__all__ = [
    "EmbeddedRunLaneController",
    "LaneParams",
    "TParams",
    "create_embedded_run_lane_controller",
    "set_create_embedded_run_lane_controller_hook",
]
