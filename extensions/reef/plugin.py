"""Reef channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Ok, Result

from .src.flow import FlowPacket, FlowReceipt


@dataclass(frozen=True, slots=True)
class ReefPlugin(ChannelPlugin):
    """Reef decentralized transport channel descriptor."""

    id: str = "reef"
    name: str = "Reef"
    kind: str = "channel"
    base_url: str = "reef://local"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send a flow packet to a peer or decentralized storage."""
        node_id = self.metadata.get("nodeId", "node_local")
        payload = {"data": message} if not isinstance(message, dict) else message
        packet = FlowPacket(sender_id=node_id, recipient_id=target, payload=payload)
        receipt = FlowReceipt(flow_id=packet.flow_id, recipient_id=target)
        return Ok(
            {
                "flow_id": packet.flow_id,
                "hash": packet.compute_hash(),
                "status": receipt.status,
                "target": target,
            }
        )

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Reef flow packets."""
        return None


reef_plugin = ReefPlugin()
entry = reef_plugin
plugin = reef_plugin
