"""jarvis.agents.sessions.tools.screen_tool - screen tool implementation.

OpenClaw parity: mirrors ``openclaw-main/src/agents/tools/screen-tool.ts``.

Allows the agent to arrange the browser-based Control UI via gateway events.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from .tool_definition_wrapper import AgentTool

ACTIONS = (
    "split_right",
    "split_down",
    "close_pane",
    "focus",
    "sidebar_show",
    "sidebar_hide",
    "terminal_show",
    "terminal_hide",
    "browser_show",
    "browser_hide",
    "navigate",
)

def create_screen_tool_definition() -> dict:
    return {
        "name": "screen",
        "description": "Drive operator web UI. Split panes, focus, panels, sidebar, navigate. Needs connected web client.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(ACTIONS),
                    "description": "Action"
                },
                "sessionKey": {
                    "type": "string",
                    "description": "Session. Default: current"
                },
                "dock": {
                    "type": "string",
                    "enum": ["bottom", "right"],
                    "description": "Panel dock on show"
                }
            },
            "required": ["action"],
        },
    }

def _resolve_session_key(params: dict, agent_session_key: str) -> str:
    session_key = params.get("sessionKey") or (agent_session_key.strip() if agent_session_key else None)
    if not session_key:
        raise ValueError("sessionKey required")
    return session_key

def _read_dock(params: dict) -> str | None:
    dock = params.get("dock")
    if dock is None or dock in ("bottom", "right"):
        return dock
    raise ValueError("dock must be bottom or right")

def _command_for_action(action: str, params: dict, agent_session_key: str) -> dict:
    if action in ("split_right", "split_down"):
        return {
            "kind": "split",
            "direction": "right" if action == "split_right" else "down",
            "sessionKey": _resolve_session_key(params, agent_session_key),
        }
    if action in ("close_pane", "focus", "navigate"):
        return {
            "kind": "close-pane" if action == "close_pane" else action,
            "sessionKey": _resolve_session_key(params, agent_session_key),
        }
    if action in ("sidebar_show", "sidebar_hide"):
        return {
            "kind": "sidebar",
            "visible": action == "sidebar_show",
        }
    if action in ("terminal_show", "terminal_hide", "browser_show", "browser_hide"):
        open_panel = action.endswith("_show")
        dock = _read_dock(params) if open_panel else None
        
        cmd = {
            "kind": "panel",
            "panel": "terminal" if action.startswith("terminal_") else "browser",
            "open": open_panel,
        }
        if dock:
            cmd["dock"] = dock
        return cmd
        
    raise ValueError(f"Unknown action: {action}")

def create_screen_tool(options: dict) -> AgentTool:
    gateway_call = options.get("gateway_call")
    agent_session_key = options.get("session_key", "")
    definition = create_screen_tool_definition()

    async def _execute(
        tool_call_id: str, params: dict, signal: Any, on_update: Any
    ) -> Any:
        if not gateway_call:
            raise RuntimeError("screen tool requires gateway_call in options")

        action = params.get("action")
        if not action or action not in ACTIONS:
            raise ValueError(f"Invalid or missing action. Must be one of: {', '.join(ACTIONS)}")

        command = _command_for_action(action, params, agent_session_key)
        payload: Dict[str, Any] = {"command": command}
        if agent_session_key:
            payload["sessionKey"] = agent_session_key

        result = await gateway_call("ui.command", payload)
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    definition["execute"] = _execute
    return {
        "name": definition["name"],
        "label": definition["name"].capitalize(),
        "description": definition["description"],
        "parameters": definition["inputSchema"],
        "execute": _execute,
    }

__all__ = ["create_screen_tool", "create_screen_tool_definition"]
