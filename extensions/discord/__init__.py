"""JARVIS Discord channel extension (Phase 5.15 minimum scaffold).

OpenClaw parity: mirrors the surface shape of
``openclaw-main/extensions/discord/index.ts`` (631 files
in the OpenClaw source). The Python port ships a minimal
``ChannelPlugin`` stub + runtime + doctor contract so the
extension is loadable + testable. The full discord SDK
surface (account-inspect, voice transcripts, subagent
hooks, activities, message routing, slash commands, etc.)
will land incrementally in the Phase 5.16 channel port.

This file is the entrypoint. ``plugin.py`` defines the
``ChannelPlugin``; ``runtime.py`` exposes the long-poll
loop; ``doctor.py`` is the diagnostic contract the host
calls to verify the channel is wired.
"""
from __future__ import annotations

from .doctor import discord_doctor_contract
from .plugin import entry, discord_plugin
from .runtime import DiscordRuntime, set_discord_runtime

__all__ = [
    "DiscordRuntime",
    "discord_doctor_contract",
    "discord_plugin",
    "entry",
    "set_discord_runtime",
]
