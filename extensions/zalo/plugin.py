"""Zalo channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.client import ZaloClient


@dataclass(frozen=True, slots=True)
class ZaloPlugin(ChannelPlugin):
    """Zalo channel descriptor."""

    id: str = "zalo"
    name: str = "Zalo"
    kind: str = "channel"
    base_url: str = "https://openapi.zalo.me"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message to Zalo user."""
        token = self.metadata.get("accessToken", "")
        client = ZaloClient(access_token=token)
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        res = client.send_text(user_id=target, text=text)
        if res.get("error", 0) != 0 and res.get("error") != "0":
            return Err(res.get("message", "send_failed"), code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Zalo events."""
        return None


zalo_plugin = ZaloPlugin()
entry = zalo_plugin
plugin = zalo_plugin
