"""Gateway RPC handlers for channels operations — mirrors OpenClaw server-methods/channels.ts."""

from __future__ import annotations

import logging
from typing import Any

from jarvis_config_core import load_config

_log = logging.getLogger("jarvis.gateway.channels_handlers")

_KNOWN_CHANNELS = [
    {"id": "desktop", "name": "Desktop HUD", "type": "desktop"},
    {"id": "cli", "name": "CLI Gateway", "type": "cli"},
    {"id": "telegram", "name": "Telegram Bot", "type": "chat"},
    {"id": "discord", "name": "Discord Bot", "type": "chat"},
    {"id": "slack", "name": "Slack App", "type": "chat"},
    {"id": "whatsapp", "name": "WhatsApp Bridge", "type": "chat"},
]


def channels_status_handler(params: dict[str, Any]) -> dict[str, Any]:
    """Handle channels.status RPC request."""
    cfg = load_config()
    bindings = getattr(cfg, "bindings", [])

    channels = []
    bound_channel_ids = {b.match.channel for b in bindings if getattr(b, "match", None) and b.match.channel}

    for ch in _KNOWN_CHANNELS:
        ch_id = ch["id"]
        is_active = ch_id in {"desktop", "cli"} or ch_id in bound_channel_ids
        channels.append(
            {
                "id": ch_id,
                "name": ch["name"],
                "type": ch["type"],
                "status": "connected" if is_active else "disconnected",
                "configured": is_active,
            }
        )

    return {
        "ok": True,
        "channels": channels,
    }


def make_channels_handlers() -> dict[str, Any]:
    """Return all channels-related gateway RPC handlers."""
    return {
        "channels.status": channels_status_handler,
        "channels.list": channels_status_handler,
    }


__all__ = ["make_channels_handlers"]
