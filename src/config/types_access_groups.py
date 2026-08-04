"""jarvis.config.types_access_groups — access-group config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.access-groups.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class DiscordChannelAudienceAccessGroup(TypedDict, total=False):
    """Discord dynamic audience backed by guild channel viewers."""

    type: str  # "discord.channelAudience"
    guildId: str
    channelId: str
    membership: str  # "canViewChannel"


class MessageSendersAccessGroup(TypedDict, total=False):
    """Static sender allowlists referenced by accessGroup:<name>."""

    type: str  # "message.senders"
    members: dict


#: A union of access-group kinds; the Python port uses a dict shape.
AccessGroupConfig = dict  # DiscordChannelAudienceAccessGroup | MessageSendersAccessGroup

#: A map of access-group name to config.
AccessGroupsConfig = dict  # str -> AccessGroupConfig


__all__ = [
    "DiscordChannelAudienceAccessGroup",
    "MessageSendersAccessGroup",
    "AccessGroupConfig",
    "AccessGroupsConfig",
]
