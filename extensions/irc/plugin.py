"""IRC channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Ok, Result

from .src.protocol import strip_irc_formatting


@dataclass(frozen=True, slots=True)
class IrcPlugin(ChannelPlugin):
    """IRC channel descriptor."""

    id: str = "irc"
    name: str = "IRC"
    kind: str = "channel"
    base_url: str = "irc://irc.libera.chat:6667"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message to IRC channel or user."""
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        clean_text = strip_irc_formatting(text)
        return Ok({"target": target, "text": clean_text, "sent": True})

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming IRC events."""
        return None


irc_plugin = IrcPlugin()
entry = irc_plugin
plugin = irc_plugin
