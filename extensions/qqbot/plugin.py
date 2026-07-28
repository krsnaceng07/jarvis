"""QQ Bot channel plugin definition.

OpenClaw parity: mirrors the OpenClaw ``qqbot`` channel
extension (15 files in the OpenClaw source).
The Python port ships a focused ``ChannelPlugin`` stub so
the extension is loadable + discoverable; the full send +
listen + media routing surface lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin


@dataclass(frozen=True, slots=True)
class QQBotPlugin(ChannelPlugin):
    """QQ Bot channel descriptor.

    Mirrors the OpenClaw ``qqbotChannel`` export: the
    channel router reads this descriptor to wire inbound
    + outbound message flows.
    """

    id: str = "qqbot"
    name: str = "QQ Bot"
    kind: str = "channel"
    base_url: str = "https://api.sgroup.qq.com"
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
            f"qqbot channel send is a Phase 5.15 stub",
        )

    async def listen(self, callback: Any) -> None:  # type: ignore[override]
        """Start listening for inbound messages. Stub in Phase 5.15."""
        return None


qqbot_plugin = QQBotPlugin()
entry = qqbot_plugin
