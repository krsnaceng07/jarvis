"""LINE channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.client import LineClient


@dataclass(frozen=True, slots=True)
class LinePlugin(ChannelPlugin):
    """LINE channel descriptor."""

    id: str = "line"
    name: str = "LINE"
    kind: str = "channel"
    base_url: str = "https://api.line.me/v2/bot"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send push message to LINE target user/group."""
        token = self.metadata.get("channelAccessToken", "")
        client = LineClient(channel_access_token=token)
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        res = client.push_text(to=target, text=text)
        if "error" in res:
            return Err(res["error"], code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming LINE webhook events."""
        return None


line_plugin = LinePlugin()
entry = line_plugin
plugin = line_plugin
