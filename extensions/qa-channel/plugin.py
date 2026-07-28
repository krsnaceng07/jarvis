"""QA Channel channel plugin definition.

OpenClaw parity: mirrors the OpenClaw ``qa-channel`` channel
extension (31 files in the OpenClaw source).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin


@dataclass(frozen=True, slots=True)
class QAChannelPlugin(ChannelPlugin):
    """QA Channel channel descriptor."""

    id: str = "qa-channel"
    name: str = "QA Channel"
    kind: str = "channel"
    base_url: str = "ws://localhost:7777"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel init hook (auth + connection). Stub in Phase 5.15."""
        return None

    async def send(self, target: str, message: Any):  # type: ignore[override]
        """Send a message to a target on this channel. Stub in Phase 5.15."""
        from jarvis_sdk import Result

        return Result.err(
            "channel_stub",
            f"qa-channel channel send is a Phase 5.15 stub",
        )

    async def listen(self, callback: Any) -> None:  # type: ignore[override]
        """Start listening for inbound messages. Stub in Phase 5.15."""
        return None


qa_channel_plugin = QAChannelPlugin()
entry = qa_channel_plugin
