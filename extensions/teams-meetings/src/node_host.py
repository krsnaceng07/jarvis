"""Node host bridge helpers for Teams Meetings."""

from __future__ import annotations

from typing import Any


def register_teams_meetings_node_handlers(runtime: Any) -> None:
    """Register `teamsmeetings.chrome` on node host if capable."""
    if hasattr(runtime, "register_node_command"):
        from .transports.teams_platform_constants import TEAMS_MEETINGS_NODE_COMMAND

        runtime.register_node_command(
            TEAMS_MEETINGS_NODE_COMMAND,
            lambda params: {"ok": True, "handled": True},
        )
