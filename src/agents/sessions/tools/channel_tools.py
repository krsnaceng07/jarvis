"""jarvis.agents.sessions.tools.channel_tools — Channel configuration and status tools.

OpenClaw parity:
Enables the agent to dynamically configure, validate, and connect messaging channels
(such as Telegram) when users provide tokens or commands, starting the live listener
without requiring manual CLI commands or process restarts.
"""

from __future__ import annotations

from typing import Any

from src.channels.channel_manager import ChannelManager


def create_configure_channel_definition() -> dict[str, Any]:
    return {
        "name": "configure_channel",
        "description": (
            "Configure, validate, and connect an external messaging channel (e.g. Telegram). "
            "Use this tool WHENEVER the user provides a channel bot token (e.g. Telegram Bot token from @BotFather) "
            "or asks to configure/connect a messaging bot. "
            "This tool validates the token against the official API, writes canonical configuration "
            "to ~/.jarvis/config.json, and automatically starts the live listener so incoming messages "
            "flow directly into JARVIS."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "channel": {
                    "type": "STRING",
                    "description": "Messaging channel identifier (e.g. 'telegram').",
                },
                "token": {
                    "type": "STRING",
                    "description": "Bot API token (e.g. Telegram token from @BotFather).",
                },
                "dm_policy": {
                    "type": "STRING",
                    "description": "Direct message access policy: 'open' (allow all users), 'allowlist', or 'pairing'. Default 'open'.",
                },
                "allow_from": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional list of allowed user IDs or handles.",
                },
            },
            "required": ["channel", "token"],
        },
    }


def create_channel_status_definition() -> dict[str, Any]:
    return {
        "name": "channel_status",
        "description": (
            "Inspect the configuration, verification, and live listener status of messaging channels "
            "(e.g. Telegram). Use this to check whether a bot is connected and listening."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "channel": {
                    "type": "STRING",
                    "description": "Optional channel name to query (e.g. 'telegram'). If omitted, returns all channels.",
                },
            },
        },
    }


CHANNEL_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    create_configure_channel_definition(),
    create_channel_status_definition(),
]


def create_configure_channel_tool(live_host: Any = None) -> dict[str, Any]:
    """Factory creating the configure_channel AgentTool."""
    definition = create_configure_channel_definition()
    manager = ChannelManager.get_instance()
    if live_host is not None:
        manager.set_live_host(live_host)

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip().lower()
        token = str(
            params.get("token") or params.get("bot_token") or params.get("botToken") or ""
        ).strip()
        dm_policy = str(params.get("dm_policy") or "open").strip().lower()
        allow_from = params.get("allow_from")

        if not channel:
            return {"content": [{"type": "text", "text": "Error: 'channel' parameter is required."}]}
        if not token:
            return {"content": [{"type": "text", "text": "Error: 'token' parameter is required."}]}

        result = await manager.configure_channel(
            channel=channel,
            token=token,
            dm_policy=dm_policy,
            allow_from=allow_from,
        )

        if not result.get("ok"):
            err_msg = result.get("error", "Channel configuration failed.")
            return {
                "content": [{"type": "text", "text": f"❌ {err_msg}"}],
                "result": f"Error: {err_msg}",
            }

        msg = result.get("message", "Channel configured and listening.")
        bot_user = result.get("bot_username", "")
        bot_id = result.get("bot_id", "")
        status = result.get("status", "")

        return {
            "content": [{"type": "text", "text": f"✅ {msg}"}],
            "data": {
                "channel": channel,
                "bot_username": bot_user,
                "bot_id": bot_id,
                "status": status,
            },
            "result": msg,
        }

    return {
        "name": definition["name"],
        "label": "Configure Channel",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


def create_channel_status_tool() -> dict[str, Any]:
    """Factory creating the channel_status AgentTool."""
    definition = create_channel_status_definition()
    manager = ChannelManager.get_instance()

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> dict[str, Any]:
        channel = params.get("channel")
        status = manager.get_channel_status(channel)
        import json

        text = json.dumps(status, indent=2)
        return {
            "content": [{"type": "text", "text": text}],
            "data": status,
            "result": text,
        }

    return {
        "name": definition["name"],
        "label": "Channel Status",
        "description": definition["description"],
        "parameters": definition["parameters"],
        "execute": _execute,
    }


__all__ = [
    "CHANNEL_TOOL_DECLARATIONS",
    "create_channel_status_definition",
    "create_channel_status_tool",
    "create_configure_channel_definition",
    "create_configure_channel_tool",
]
