"""jarvis.config.types_discord_presence — Discord presence-event config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.discord-presence.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class DiscordPresenceEventsConfig(TypedDict, total=False):
    """Online-presence system events for a Discord guild."""

    enabled: bool
    channelId: str
    users: list
    reconnectSuppressSeconds: int
    burstLimit: int
    burstWindowSeconds: int


__all__ = ["DiscordPresenceEventsConfig"]
