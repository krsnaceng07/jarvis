"""Google Chat channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.client import GoogleChatClient


@dataclass(frozen=True, slots=True)
class GoogleChatPlugin(ChannelPlugin):
    """Google Chat channel descriptor."""

    id: str = "googlechat"
    name: str = "Google Chat"
    kind: str = "channel"
    base_url: str = "https://chat.googleapis.com/v1"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message to Google Chat webhook or space."""
        client = GoogleChatClient(webhook_url=target if target.startswith("http") else None)
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        res = client.send_text(target, text)
        if "error" in res:
            return Err(res["error"], code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Google Chat webhook events."""
        return None


googlechat_plugin = GoogleChatPlugin()
entry = googlechat_plugin
plugin = googlechat_plugin
