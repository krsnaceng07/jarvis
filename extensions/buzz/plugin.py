"""Buzz channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Ok, Result

from .src.rooms import BuzzRoomManager


@dataclass(frozen=True, slots=True)
class BuzzPlugin(ChannelPlugin):
    """Buzz gossip channel descriptor."""

    id: str = "buzz"
    name: str = "Buzz"
    kind: str = "channel"
    base_url: str = "buzz://mesh"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Broadcast message to a Buzz gossip room."""
        node_id = self.metadata.get("nodeId", "node_primary")
        mgr = BuzzRoomManager(node_id=node_id)
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        msg = mgr.broadcast(room_id=target, content=text)
        return Ok(msg.to_dict())

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming gossip mesh events."""
        return None


buzz_plugin = BuzzPlugin()
entry = buzz_plugin
plugin = buzz_plugin
