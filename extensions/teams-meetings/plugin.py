"""Teams Meetings plugin entry and lifecycle definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin

from .src.cli import register_teams_meetings_cli
from .src.cli_command_context import TeamsMeetingsCliContext
from .src.config import resolve_teams_meetings_config
from .src.doctor import run_teams_meetings_doctor
from .src.node_invoke_policy import create_teams_meetings_chrome_node_invoke_policy
from .src.plugin_registration import (
    register_teams_meetings_plugin,
)
from .src.runtime import TeamsMeetingsRuntime
from .src.transports.teams_platform_constants import (
    TEAMS_MEETINGS_NODE_COMMAND,
)


@dataclass(slots=True)
class TeamsMeetingsPlugin(Plugin):
    """Teams Meetings extension plugin for Microsoft Teams browser participation."""

    id: str = "teams-meetings"
    name: str = "Teams Meetings"
    description: str = (
        "Join Microsoft Teams meetings (work links under teams.microsoft.com/l/meetup-join/... "
        "and consumer links under teams.live.com/meet/...) as a guest in the browser."
    )
    version: str = "0.1.0"
    author: str = "OpenClaw Authors / JARVIS Contributors"
    tags: list[str] = field(
        default_factory=lambda: ["teams", "meetings", "browser", "voice", "transcripts"]
    )

    def init(self, ctx: Any) -> None:
        raw_config = getattr(ctx, "config", {}) if ctx else {}
        runtime = getattr(ctx, "runtime", None) if ctx else None

        if runtime is None:
            runtime = TeamsMeetingsRuntime(
                config=raw_config,
                full_config=getattr(ctx, "full_config", None),
                runtime=ctx,
            )

        register_tool = getattr(ctx, "register_tool", None) if ctx else None
        register_gateway = getattr(ctx, "register_gateway_method", None) if ctx else None
        register_cli = getattr(ctx, "register_cli_handler", None) if ctx else None

        register_teams_meetings_plugin(
            register_tool=register_tool,
            register_gateway_method=register_gateway,
            register_cli_handler=register_cli,
            runtime=runtime,
            raw_config=raw_config,
        )

        if hasattr(ctx, "register_cli_parser"):
            ctx.register_cli_parser(
                lambda subparsers: register_teams_meetings_cli(
                    subparsers,
                    lambda: TeamsMeetingsCliContext(
                        config=raw_config,
                        runtime=runtime,
                    ),
                )
            )

        if hasattr(ctx, "register_node_invoke_policy"):
            cfg_res = resolve_teams_meetings_config(raw_config)
            cfg = cfg_res.unwrap() if cfg_res.is_ok else None
            policy = create_teams_meetings_chrome_node_invoke_policy(cfg)
            ctx.register_node_invoke_policy(TEAMS_MEETINGS_NODE_COMMAND, policy)

        if hasattr(ctx, "register_doctor_contract"):
            ctx.register_doctor_contract(
                "teams-meetings",
                lambda config, fix=False: run_teams_meetings_doctor(config=config, fix=fix),
            )


teams_meetings_plugin = TeamsMeetingsPlugin()
entry = teams_meetings_plugin
