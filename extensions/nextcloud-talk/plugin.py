"""Nextcloud Talk channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Err, Ok, Result

from .src.client import NextcloudTalkClient


@dataclass(frozen=True, slots=True)
class NextcloudTalkPlugin(ChannelPlugin):
    """Nextcloud Talk channel descriptor."""

    id: str = "nextcloud-talk"
    name: str = "Nextcloud Talk"
    kind: str = "channel"
    base_url: str = "https://cloud.example.com"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send message to Nextcloud Talk room."""
        client = NextcloudTalkClient(
            server_url=self.metadata.get("serverUrl", self.base_url),
            username=self.metadata.get("username"),
            password=self.metadata.get("password"),
        )
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        reply_to = (
            message.get("replyTo") or message.get("reply_to") if isinstance(message, dict) else None
        )
        res = client.send_chat_message(room_token=target, message=text, reply_to=reply_to)
        if "error" in res:
            return Err(res["error"], code="SEND_FAILED")
        return Ok(res)

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Nextcloud Talk webhook events."""
        return None


nextcloud_talk_plugin = NextcloudTalkPlugin()
entry = nextcloud_talk_plugin
plugin = nextcloud_talk_plugin
