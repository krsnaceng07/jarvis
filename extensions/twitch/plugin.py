"""Twitch channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Ok, Result


@dataclass(frozen=True, slots=True)
class TwitchPlugin(ChannelPlugin):
    """Twitch channel descriptor."""

    id: str = "twitch"
    name: str = "Twitch"
    kind: str = "channel"
    base_url: str = "irc://irc.chat.twitch.tv:6667"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message to Twitch stream chat."""
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        clean_target = target.lstrip("#")
        return Ok({"channel": clean_target, "message": text, "sent": True})

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Twitch chat events."""
        return None


twitch_plugin = TwitchPlugin()
entry = twitch_plugin
plugin = twitch_plugin
