"""ClickClack channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Ok, Result

from .src.session import ClickClackSession


@dataclass(frozen=True, slots=True)
class ClickClackPlugin(ChannelPlugin):
    """ClickClack terminal channel descriptor."""

    id: str = "clickclack"
    name: str = "ClickClack"
    kind: str = "channel"
    base_url: str = "http://localhost:7433/clickclack"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Send interactive message or command to terminal session."""
        session = ClickClackSession(session_id=target)
        session.touch()
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")
        return Ok({"session_id": target, "text": text, "dispatched": True})

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming terminal interactions."""
        return None


clickclack_plugin = ClickClackPlugin()
entry = clickclack_plugin
plugin = clickclack_plugin
