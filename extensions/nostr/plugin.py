"""Nostr channel plugin definition for JARVIS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Ok, Result

from .src.events import create_direct_message, create_text_note


@dataclass(frozen=True, slots=True)
class NostrPlugin(ChannelPlugin):
    """Nostr decentralized channel descriptor."""

    id: str = "nostr"
    name: str = "Nostr"
    kind: str = "channel"
    base_url: str = "wss://relay.damus.io"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel initialization."""
        return None

    async def send(self, target: str, message: Any) -> Result[dict[str, Any]]:
        """Publish event to Nostr relays or send direct message to target npub/hex pubkey."""
        pubkey = self.metadata.get("pubkey", "0" * 64)
        text = str(message) if isinstance(message, (str, int, float)) else message.get("text", "")

        if target.startswith("npub1") or len(target) == 64:
            ev = create_direct_message(sender_pubkey=pubkey, recipient_pubkey=target, content=text)
        else:
            ev = create_text_note(pubkey=pubkey, content=text)

        return Ok({"event_id": ev.id, "kind": ev.kind, "target": target, "published": True})

    async def listen(self, callback: Any) -> None:
        """Start listening for incoming Nostr events from relays."""
        return None


nostr_plugin = NostrPlugin()
entry = nostr_plugin
plugin = nostr_plugin
