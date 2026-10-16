"""Plugin capability metadata and gateway method registration for Teams Meetings."""

from __future__ import annotations

from typing import Any

from .plugin_helpers import execute_teams_meetings_action
from .plugin_schema import TEAMS_MEETINGS_TOOL_SCHEMA
from .transports.teams_platform_constants import (
    TEAMS_MEETINGS_TOOL_NAME,
)

TEAMS_MEETINGS_GATEWAY_METHODS: list[dict[str, Any]] = [
    {
        "method": "teamsmeetings.join",
        "description": "Join a Microsoft Teams meeting room.",
    },
    {
        "method": "teamsmeetings.leave",
        "description": "Leave active Microsoft Teams meeting.",
    },
    {
        "method": "teamsmeetings.status",
        "description": "Get active Microsoft Teams session status.",
    },
    {
        "method": "teamsmeetings.transcript",
        "description": "Get live transcript lines from active Microsoft Teams meeting.",
    },
    {
        "method": "teamsmeetings.speak",
        "description": "Speak text into active Microsoft Teams meeting.",
    },
    {
        "method": "teamsmeetings.recoverTab",
        "description": "Recover and inspect Microsoft Teams browser tab.",
    },
    {
        "method": "teamsmeetings.setup",
        "description": "Verify Microsoft Teams runtime environment and node status.",
    },
]


def register_teams_meetings_plugin(
    *,
    register_tool: Any = None,
    register_gateway_method: Any = None,
    register_cli_handler: Any = None,
    runtime: Any = None,
    raw_config: dict[str, Any] | None = None,
) -> None:
    cfg = raw_config or {}

    if register_tool:

        async def tool_handler(params: dict[str, Any]) -> dict[str, Any]:
            action = params.get("action", "status")
            return await execute_teams_meetings_action(
                action_name=action,
                params=params,
                raw_config=cfg,
                runtime=runtime,
            )

        register_tool(
            name=TEAMS_MEETINGS_TOOL_NAME,
            schema=TEAMS_MEETINGS_TOOL_SCHEMA,
            handler=tool_handler,
        )

    if register_gateway_method:
        action_map = {
            "teamsmeetings.join": "join",
            "teamsmeetings.leave": "leave",
            "teamsmeetings.status": "status",
            "teamsmeetings.transcript": "transcript",
            "teamsmeetings.speak": "speak",
            "teamsmeetings.recoverTab": "recover_current_tab",
            "teamsmeetings.setup": "setup",
        }
        for method_name, action_name in action_map.items():

            def make_handler(act: str):
                async def rpc_handler(payload: dict[str, Any]) -> dict[str, Any]:
                    return await execute_teams_meetings_action(
                        action_name=act,
                        params=payload or {},
                        raw_config=cfg,
                        runtime=runtime,
                    )

                return rpc_handler

            register_gateway_method(
                method=method_name,
                handler=make_handler(action_name),
            )
