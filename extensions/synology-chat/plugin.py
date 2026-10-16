"""Synology Chat channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.client import SynologyChatClient


@dataclass(frozen=True, slots=True)
class SynologyChatPlugin(ChannelPlugin):
    """Synology Chat channel descriptor."""

    id: str = "synology-chat"
    name: str = "Synology Chat"
    kind: str = "channel"
    base_url: str = "https://nas.local"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message via Synology Chat incoming webhook."""
        url = target if target.startswith("http") else self.metadata.get("incomingUrl", "")
        client = SynologyChatClient(incoming_url=url)
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        user_ids = message.get("user_ids") if isinstance(message, dict) else None
        res = client.send_message(text=text, user_ids=user_ids)
        if "error" in res:
            return Err(res["error"], code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Synology Chat events."""
        return None


synology_chat_plugin = SynologyChatPlugin()
entry = synology_chat_plugin
plugin = synology_chat_plugin
