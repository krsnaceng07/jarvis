"""Zalo Personal Account channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.session import ZaloUserSession
from .src.client import ZaloUserClient


@dataclass(frozen=True, slots=True)
class ZaloUserPlugin(ChannelPlugin):
    """Zalo personal account descriptor."""

    id: str = "zalouser"
    name: str = "Zalo Personal Account"
    kind: str = "channel"
    base_url: str = "https://chat.zalo.me"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send direct message on Zalo Personal Account."""
        session = ZaloUserSession(
            imei=self.metadata.get("imei", "default-imei"),
            cookie=self.metadata.get("cookie", "default-cookie"),
            logged_in=True,
        )
        client = ZaloUserClient(session=session)
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        res = client.send_direct_message(recipient_id=target, text=text)
        if "error" in res:
            return Err(res["error"], code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Zalo personal chat events."""
        return None


zalouser_plugin = ZaloUserPlugin()
entry = zalouser_plugin
plugin = zalouser_plugin
