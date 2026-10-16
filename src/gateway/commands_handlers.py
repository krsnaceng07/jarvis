"""Gateway RPC handlers for commands operations — mirrors OpenClaw server-methods/commands.ts."""

from __future__ import annotations

import logging
from typing import Any

from src.commands.commands_registry import DIRECTIVES, INLINE_SHORTCUTS

_log = logging.getLogger("jarvis.gateway.commands_handlers")

_CORE_COMMANDS = [
    {"name": "/help", "description": "Show available commands and usage guide", "category": "session"},
    {"name": "/status", "description": "Show current system status and health", "category": "status"},
    {"name": "/reset", "description": "Reset the current session context", "category": "session"},
    {"name": "/think", "description": "Enable deep thinking / reasoning mode", "category": "options"},
    {"name": "/fast", "description": "Enable fast generation mode", "category": "options"},
    {"name": "/model", "description": "Show or switch active LLM model", "category": "options"},
    {"name": "/whoami", "description": "Display user identity and profile", "category": "status"},
    {"name": "/btw", "description": "Ask a side question without polluting history", "category": "session"},
]


def commands_list_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle commands.list RPC request."""
    commands = list(_CORE_COMMANDS)
    return {
        "ok": True,
        "count": len(commands),
        "commands": commands,
        "directives": sorted(DIRECTIVES),
        "shortcuts": sorted(INLINE_SHORTCUTS),
    }


def make_commands_handlers() -> dict[str, Any]:
    """Return all commands-related gateway RPC handlers."""
    return {
        "commands.list": commands_list_handler,
    }


__all__ = ["make_commands_handlers"]
