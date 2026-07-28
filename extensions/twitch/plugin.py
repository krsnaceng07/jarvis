"""Twitch channel plugin definition.

OpenClaw parity: mirrors the OpenClaw ``twitch`` channel
extension (12 files in the OpenClaw source).
The Python port ships a focused ``ChannelPlugin`` stub so
the extension is loadable + discoverable; the full send +
listen + media routing surface lands in Phase 5.16+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin


@dataclass(frozen=True, slots=True)
class TwitchPlugin(ChannelPlugin):
    """Twitch channel descriptor.

    Mirrors the OpenClaw ``twitchChannel`` export: the
    channel router reads this descriptor to wire inbound
    + outbound message flows.
    """

    id: str = "twitch"
    name: str = "Twitch"
    kind: str = "channel"
    base_url: str = "wss://irc.chat.twitch.tv:443"
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
            f"twitch channel send is a Phase 5.15 stub",
        )

    async def listen(self, callback: Any) -> None:  # type: ignore[override]
        """Start listening for inbound messages. Stub in Phase 5.15."""
        return None


twitch_plugin = TwitchPlugin()
entry = twitch_plugin
