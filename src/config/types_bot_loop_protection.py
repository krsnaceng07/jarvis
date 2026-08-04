"""jarvis.config.types_bot_loop_protection — bot-loop protection config types.

OpenClaw parity: mirrors
``openclaw-main/src/config/types.bot-loop-protection.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class ChannelBotLoopProtectionConfig(TypedDict, total=False):
    """Pair loop-protection config for channels that support it."""

    enabled: bool
    maxEventsPerWindow: int
    windowSeconds: int
    cooldownSeconds: int


__all__ = ["ChannelBotLoopProtectionConfig"]
