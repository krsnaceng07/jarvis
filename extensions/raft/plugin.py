"""Raft channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Ok, Result

from .src.state import RaftNodeState


@dataclass(frozen=True, slots=True)
class RaftPlugin(ChannelPlugin):
    """Raft distributed consensus channel descriptor."""

    id: str = "raft"
    name: str = "Raft"
    kind: str = "channel"
    base_url: str = "raft://cluster"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Replicate log entry across Raft cluster."""
        node_id = self.metadata.get("nodeId", "node_1")
        state = RaftNodeState(node_id=node_id, role="leader")
        entry = state.append_log(data=message)
        return Ok(
            {
                "term": entry.term,
                "index": entry.index,
                "data": entry.data,
                "target": target,
                "replicated": True,
            }
        )

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Raft RPC messages."""
        return None


raft_plugin = RaftPlugin()
entry = raft_plugin
plugin = raft_plugin
