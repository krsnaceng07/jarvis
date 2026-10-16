"""Mattermost channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.client import MattermostClient


@dataclass(frozen=True, slots=True)
class MattermostPlugin(ChannelPlugin):
    """Mattermost channel descriptor."""

    id: str = "mattermost"
    name: str = "Mattermost"
    kind: str = "channel"
    base_url: str = "http://localhost:8065"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message to Mattermost channel or thread."""
        client = MattermostClient(
            server_url=self.metadata.get("serverUrl", self.base_url),
            bot_token=self.metadata.get("botToken"),
        )
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        root_id = message.get("root_id") if isinstance(message, dict) else None
        res = client.create_post(channel_id=target, message=text, root_id=root_id)
        if "error" in res:
            return Err(res["error"], code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Mattermost events or webhooks."""
        return None


mattermost_plugin = MattermostPlugin()
entry = mattermost_plugin
plugin = mattermost_plugin
