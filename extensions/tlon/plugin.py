"""Tlon channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.client import UrbitClient


@dataclass(frozen=True, slots=True)
class TlonPlugin(ChannelPlugin):
    """Tlon (Urbit) channel descriptor."""

    id: str = "tlon"
    name: str = "Tlon"
    kind: str = "channel"
    base_url: str = "http://localhost:8080"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message to Tlon / Urbit channel nest."""
        client = UrbitClient(
            ship_url=self.metadata.get("shipUrl", self.base_url),
            ship_name=self.metadata.get("ship", "~zod"),
            code=self.metadata.get("code", "lidlut-tabwed-pillex-ridrup"),
        )
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        res = client.post_chat(channel_nest=target, text=text)
        if "error" in res:
            return Err(res["error"], code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Tlon / Urbit messages."""
        return None


tlon_plugin = TlonPlugin()
entry = tlon_plugin
plugin = tlon_plugin
