"""Google Meet extension entry point and plugin definition.

Registers tools, CLI commands, gateway RPC methods, node host commands,
node invoke policies, doctor checks, and runtime sessions.
"""

from __future__ import annotations

import argparse
from typing import Any

from jarvis_sdk import PluginApi, define_plugin_entry

from .src.cli import register_google_meet_cli
from .src.cli_command_context import GoogleMeetCliContext
from .src.doctor import run_google_meet_doctor
from .src.node_host import handle_google_meet_node_host_command
from .src.node_invoke_policy import GoogleMeetChromeNodeInvokePolicy
from .src.plugin_helpers import execute_google_meet_action
from .src.plugin_registration import (
    GOOGLE_MEET_GATEWAY_METHOD_SPECS,
    handle_google_meet_gateway_rpc,
)
from .src.plugin_schema import GOOGLE_MEET_TOOL_SCHEMA
from .src.runtime import GoogleMeetRuntime

# Shared process-level runtime instance for Google Meet sessions
_runtime_instance: GoogleMeetRuntime | None = None


def get_google_meet_runtime(config: dict[str, Any] | None = None) -> GoogleMeetRuntime:
    """Get or instantiate the global GoogleMeetRuntime singleton."""
    global _runtime_instance
    if _runtime_instance is None:
        _runtime_instance = GoogleMeetRuntime(config=config or {})
    elif config is not None:
        _runtime_instance.update_config(config)
    return _runtime_instance


class GoogleMeetTool:
    """The Google Meet automation tool for agent interactions."""

    name: str = "google_meet"
    description: str = (
        "Google Meet automation: create spaces, join/leave meetings, speak audio, "
        "retrieve realtime transcripts, fetch recordings/notes, and calculate attendance."
    )
    parameters: dict[str, Any] = GOOGLE_MEET_TOOL_SCHEMA

    def __init__(self, runtime: GoogleMeetRuntime, raw_config: dict[str, Any]) -> None:
        self.runtime = runtime
        self.raw_config = raw_config

    async def __call__(self, args: dict[str, Any], extra: Any = None) -> dict[str, Any]:
        return await execute_google_meet_action(
            action_name=args.get("action", "status"),
            params=args,
            raw_config=self.raw_config,
            runtime=self.runtime,
        )

    async def execute(self, ctx: Any, args: dict[str, Any]) -> dict[str, Any]:
        return await execute_google_meet_action(
            action_name=args.get("action", "status"),
            params=args,
            raw_config=self.raw_config,
            runtime=self.runtime,
        )


def _register(api: PluginApi) -> None:
    """Register all Google Meet capabilities on the host PluginApi."""
    raw_config = api.config or {}
    runtime = get_google_meet_runtime(raw_config)

    # 1. Register Tool: google_meet
    tool_inst = GoogleMeetTool(runtime, raw_config)
    api.register_tool(tool_inst)

    # 2. Register CLI commands
    def _cli_registrar(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
        register_google_meet_cli(
            subparsers=subparsers,
            context_factory=lambda: GoogleMeetCliContext(
                config=api.config or {},
                runtime=runtime,
                json_mode=False,
            ),
        )

    api.register_cli(_cli_registrar)

    # 3. Register Gateway RPC methods
    for spec in GOOGLE_MEET_GATEWAY_METHOD_SPECS:
        method_name = spec["method"]

        def _make_gateway_handler(m_name: str):
            async def _handler(params: dict[str, Any]) -> dict[str, Any]:
                return await handle_google_meet_gateway_rpc(
                    method=m_name,
                    params=params,
                    raw_config=api.config or {},
                    runtime=runtime,
                )

            return _handler

        api.register_gateway_method(
            method=method_name,
            handler=_make_gateway_handler(method_name),
        )

    # 4. Register Node Host Command & Node Invoke Policy
    api.register_node_host_command(
        {
            "id": "googlemeet.chrome",
            "handler": handle_google_meet_node_host_command,
        }
    )
    api.register_node_invoke_policy(
        {
            "commands": ["googlemeet.chrome"],
            "handle": GoogleMeetChromeNodeInvokePolicy().handle,
        }
    )

    # 5. Register Doctor Contract
    async def _detect_google_meet_issues(ctx: Any = None) -> list[dict[str, Any]]:
        res = await run_google_meet_doctor(config=api.config or {}, fix=False)
        return res.value if res.is_ok else [{"id": "google-meet.error", "message": str(res.error)}]

    async def _apply_google_meet_fixes(ctx: Any = None) -> list[dict[str, Any]]:
        res = await run_google_meet_doctor(config=api.config or {}, fix=True)
        return res.value if res.is_ok else [{"id": "google-meet.error", "message": str(res.error)}]

    if hasattr(api, "register_doctor_contract"):
        api.register_doctor_contract(
            {
                "id": "google-meet.doctor",
                "version": 1,
                "detect": _detect_google_meet_issues,
                "apply": _apply_google_meet_fixes,
            }
        )


entry = define_plugin_entry(
    id="google-meet",
    kind="tools",
    name="Google Meet",
    description=(
        "Google Meet space management, browser automation, realtime audio participation, "
        "transcripts, attendance summaries, and artifact exports."
    ),
    register=_register,
)
