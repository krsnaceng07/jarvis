"""jarvis.agents.sessions.tools.message_tool — message tool implementation.

OpenClaw parity: mirrors OpenClaw's visible reply message tool.

Allows the agent to send visible messages to the user or react to messages.
"""
from __future__ import annotations

from typing import Any

from .tool_definition_wrapper import AgentTool


def create_message_tool_definition() -> dict:
    return {
        "name": "message",
        "description": (
            "Send a visible message or react to a message. "
            "The agent adds and removes emoji reactions with the `message` tool's `react` action. "
            "Behavior varies by channel.\n"
            "- emoji is required when adding a reaction.\n"
            "- Set emoji to an empty string (\"\") to remove the bot's reaction(s) on channels that support it.\n"
            "- Set remove: true to remove one specific emoji.\n"
            "- On channels with status reactions, trackToolCalls: true on a reaction lets the runtime reuse that reacted message for subsequent tool-progress reactions during the same turn.\n"
            "\n"
            "Channel behavior:\n"
            "Discord and Slack\n"
            "- Empty emoji removes all of the bot's reactions on that message.\n"
            "- remove: true removes the specific emoji.\n"
            "- Multiple reactions stack.\n"
            "WhatsApp, Signal, Zalo, Nextcloud\n"
            "- Adding an emoji replaces the bot's previous reaction.\n"
            "- Empty emoji removes the bot's reaction.\n"
            "- remove: true acts exactly like an empty emoji.\n"
            "Telegram, iMessage\n"
            "- One bot reaction per message. Setting an empty emoji removes it.\n"
            "Feishu/Lark\n"
            "- Add and remove individual emojis."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["react", "send"],
                    "description": "The action to perform. Use 'react' for emoji reactions.",
                },
                "messageId": {
                    "type": "string",
                    "description": "The ID of the message to react to. Required for 'react'.",
                },
                "emoji": {
                    "type": "string",
                    "description": "The emoji to react with. Empty string removes reactions.",
                },
                "remove": {
                    "type": "boolean",
                    "description": "If true, removes the specific emoji.",
                },
                "trackToolCalls": {
                    "type": "boolean",
                    "description": "If true, allows runtime to reuse the reacted message for tool-progress reactions.",
                },
                "text": {
                    "type": "string",
                    "description": "The text to send. Required for 'send'.",
                },
            },
            "required": ["action"],
        },
    }


def _get_session_key(session_key: str, agent_id: str) -> str:
    if session_key:
        return session_key
    if agent_id:
        return f"agent:{agent_id}"
    return "global"


def create_message_tool(options: dict) -> AgentTool:
    gateway_call = options.get("gateway_call")
    session_key = options.get("session_key", "")
    agent_id = options.get("agent_id", "")
    resolved_session_key = _get_session_key(session_key, agent_id)

    definition = create_message_tool_definition()

    async def _execute(
        tool_call_id: str, params: dict, signal: Any, on_update: Any
    ) -> Any:
        if not gateway_call:
            raise RuntimeError("message tool requires gateway_call in options")

        action = params.get("action")
        if action not in ("react", "send"):
            raise ValueError("message tool requires action to be 'react' or 'send'")

        if action == "react":
            message_id = params.get("messageId")
            if not message_id:
                raise ValueError("message tool requires messageId for 'react' action")
            
            emoji = params.get("emoji", "")
            remove = params.get("remove", False)
            track_tool_calls = params.get("trackToolCalls", False)

            try:
                await gateway_call(
                    "agent.react",
                    {
                        "sessionKey": resolved_session_key,
                        "messageId": message_id,
                        "emoji": emoji,
                        "remove": remove,
                        "trackToolCalls": track_tool_calls,
                    },
                    signal=signal,
                )
                if remove or emoji == "":
                    return {"content": [{"type": "text", "text": f"Removed reaction on {message_id}."}]}
                return {"content": [{"type": "text", "text": f"Reacted {emoji} to {message_id}."}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Failed to react: {e}"}], "isError": True}
        else:
            # action == "send"
            text = params.get("text")
            if not text:
                raise ValueError("message tool requires text for 'send' action")
            
            try:
                await gateway_call(
                    "agent.message",
                    {
                        "sessionKey": resolved_session_key,
                        "text": text,
                    },
                    signal=signal,
                )
                return {"content": [{"type": "text", "text": "Message sent."}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Failed to send message: {e}"}], "isError": True}

    return {
        "name": definition["name"],
        "description": definition["description"],
        "inputSchema": definition["inputSchema"],
        "execute": _execute,
    }

__all__ = ["create_message_tool", "create_message_tool_definition"]
