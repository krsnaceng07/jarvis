"""Discord channel plugin definition.

OpenClaw parity: mirrors ``channel-plugin-api.ts``. Defines
the ``discordPlugin`` descriptor (id, kind, hooks) the
host uses to wire Discord into the gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from jarvis_sdk import ChannelPlugin


@dataclass(frozen=True, slots=True)
class DiscordPlugin(ChannelPlugin):
    """Plugin descriptor for the Discord channel.

    Mirrors the OpenClaw ``discordPlugin`` export: the host
    reads this descriptor, registers the channel hook
    surface, and invokes the runtime on the configured poll
    interval.
    """

    id: str = "discord"
    name: str = "Discord"
    kind: str = "channel"
    poll_interval_sec: int = 2
    on_message: Callable[[Any], None] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Channel init hook (auth + config). Stub in Phase 5.15."""
        return None

    async def listen(self, callback: Any) -> None:
        """Begin the gateway poll loop. No-op in the stub."""
        if self.on_message is not None:
            self.on_message({"event": "channel.ready", "id": self.id})

    async def send(self, target: str, message: Any) -> None:
        """Send a message to a target on this channel. Stub in Phase 5.15."""
        return None

    def start(self) -> None:
        """Begin the gateway poll loop. No-op in the stub."""
        if self.on_message is not None:
            self.on_message({"event": "channel.ready", "id": self.id})


discord_plugin = DiscordPlugin()
entry = discord_plugin
