"""Zoom Meetings plugin definition and lifecycle hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Plugin

from .src.cli import register_zoom_meetings_cli
from .src.config import resolve_zoom_meetings_config
from .src.doctor import run_zoom_meetings_doctor
from .src.plugin_helpers import execute_zoom_meetings_action
from .src.runtime import ZoomMeetingsRuntime


@dataclass(slots=True)
class ZoomMeetingsPlugin(Plugin):
    """Zoom Meetings extension for joining Zoom calls as guest via the Zoom Web App."""

    id: str = "zoom-meetings"
    name: str = "Zoom Meetings"
    description: str = "Join Zoom meetings (zoom.us/j/... and account subdomains) as a guest through the Zoom Web App in the browser."
    version: str = "0.1.0"
    author: str = "OpenClaw Authors / JARVIS Contributors"
    tags: list[str] = field(
        default_factory=lambda: ["zoom", "meetings", "browser", "voice", "transcripts"]
    )

    def init(self, ctx: Any) -> None:
        raw_config = getattr(ctx, "config", {}) if ctx else {}
        runtime = getattr(ctx, "runtime", None) if ctx else None

        if runtime is None:
            cfg_res = resolve_zoom_meetings_config(raw_config)
            cfg = cfg_res.unwrap() if cfg_res.is_ok else None
            if cfg:
                runtime = ZoomMeetingsRuntime(config=cfg)

        if hasattr(ctx, "register_tool"):
            for tool in self.register_tools():
                ctx.register_tool(tool)

        if hasattr(ctx, "register_rpc_methods"):
            for rpc_name, handler in self.register_rpc_methods().items():
                ctx.register_rpc_methods(rpc_name, handler)

        if hasattr(ctx, "register_cli_parser"):
            ctx.register_cli_parser(register_zoom_meetings_cli)

        if hasattr(ctx, "register_doctor_contract"):
            ctx.register_doctor_contract(
                "zoom-meetings",
                lambda config, fix=False: run_zoom_meetings_doctor(config=config, fix=fix),
            )

    def register_tools(self) -> list[dict[str, Any]]:
        """Register the `zoom_meetings` agent tool."""
        return [
            {
                "name": "zoom_meetings",
                "description": "Join, manage, speak into, or inspect Zoom meetings as a guest.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["join", "leave", "status", "transcript", "speak"],
                            "description": "Action to execute.",
                        },
                        "url": {
                            "type": "string",
                            "description": "Zoom meeting URL (e.g. https://zoom.us/j/123456789).",
                        },
                        "name": {
                            "type": "string",
                            "description": "Guest display name.",
                        },
                        "passcode": {
                            "type": "string",
                            "description": "Meeting passcode if required.",
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["agent", "bidi", "listen", "transcribe"],
                            "description": "Participation mode.",
                        },
                        "sessionId": {
                            "type": "string",
                            "description": "Session ID for existing meeting operations.",
                        },
                        "message": {
                            "type": "string",
                            "description": "Message text to speak.",
                        },
                    },
                    "required": ["action"],
                },
                "handler": lambda params, raw_config, runtime=None: execute_zoom_meetings_action(
                    action_name=params.get("action", ""),
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                ),
            }
        ]

    def register_rpc_methods(self) -> dict[str, Any]:
        """Register Gateway RPC methods under `zoommeetings.*`."""
        return {
            "zoommeetings.join": lambda params, raw_config, runtime=None: (
                execute_zoom_meetings_action(
                    action_name="join",
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                )
            ),
            "zoommeetings.leave": lambda params, raw_config, runtime=None: (
                execute_zoom_meetings_action(
                    action_name="leave",
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                )
            ),
            "zoommeetings.status": lambda params, raw_config, runtime=None: (
                execute_zoom_meetings_action(
                    action_name="status",
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                )
            ),
            "zoommeetings.transcript": lambda params, raw_config, runtime=None: (
                execute_zoom_meetings_action(
                    action_name="transcript",
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                )
            ),
            "zoommeetings.speak": lambda params, raw_config, runtime=None: (
                execute_zoom_meetings_action(
                    action_name="speak",
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                )
            ),
            "zoommeetings.setup": lambda params, raw_config, runtime=None: (
                execute_zoom_meetings_action(
                    action_name="setup",
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                )
            ),
            "zoommeetings.doctor": lambda params, raw_config, runtime=None: (
                execute_zoom_meetings_action(
                    action_name="doctor",
                    params=params,
                    raw_config=raw_config,
                    runtime=runtime,
                )
            ),
        }


zoom_meetings_plugin = ZoomMeetingsPlugin()
entry = zoom_meetings_plugin
