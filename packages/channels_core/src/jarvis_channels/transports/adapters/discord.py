"""Discord server-side channel transport adapter for Track 3.5.

Enforces:
- Invariant T35-04: Server-side channel transport adapter.
- Invariant T35-05: Server-authoritative route triple (discord, user_id, channel_or_thread_id).
- Invariant T35-06: Button components for interactive decision turns.
- Invariant T35-15: 6-state delivery tracking.
- Invariant T35-16: SQLite WAL atomic claim deduplication.
"""

from __future__ import annotations

from typing import Any, Callable, Optional
import uuid

from jarvis_channels.transports.base import BaseChannelTransport
from jarvis_channels.transports.deduplication import ChannelInboundDeduplicator
from jarvis_channels.transports.delivery import ChannelDeliveryTracker
from jarvis_channels.types import OutboundMessage


class DiscordTransportAdapter(BaseChannelTransport):
    """Server-side transport adapter for Discord bot integration."""

    def __init__(
        self,
        deduplicator: ChannelInboundDeduplicator,
        tracker: ChannelDeliveryTracker,
        provider_send_fn: Optional[
            Callable[[dict[str, Any]], tuple[bool, Optional[str], Optional[str]]]
        ] = None,
    ) -> None:
        super().__init__(
            channel_id="discord",
            deduplicator=deduplicator,
            tracker=tracker,
        )
        self._provider_send_fn = provider_send_fn

    def parse_inbound_raw(
        self,
        raw_event: dict[str, Any],
    ) -> tuple[str, str, Optional[str], str, dict[str, Any]] | None:
        """Parse Discord event (MESSAGE_CREATE or INTERACTION_CREATE) into canonical fields."""
        # Check interaction component (button clicks)
        if raw_event.get("type") == 3:  # MESSAGE_COMPONENT
            msg_id = str(raw_event.get("id"))
            user = raw_event.get("member", {}).get("user") or raw_event.get("user", {})
            user_id = str(user.get("id", "unknown"))
            channel_id = str(raw_event.get("channel_id", "root"))
            custom_id = raw_event.get("data", {}).get("custom_id", "")
            return (msg_id, user_id, channel_id, custom_id, {"interaction_id": raw_event.get("id")})

        msg_id = str(raw_event.get("id", ""))
        author = raw_event.get("author", {})
        user_id = str(author.get("id", "unknown"))
        channel_id = str(raw_event.get("channel_id", "root"))
        # Ignore bot messages
        if author.get("bot", False):
            return None
        text = raw_event.get("content", "")
        return (msg_id, user_id, channel_id, text, {"guild_id": raw_event.get("guild_id")})

    def format_native_outbound(self, message: OutboundMessage) -> dict[str, Any]:
        """Format OutboundMessage into Discord Create Message payload with ActionRow components."""
        payload: dict[str, Any] = {
            "channel_id": message.conversation_id,
            "content": message.text,
        }
        if message.reply_to_id:
            payload["message_reference"] = {"message_id": message.reply_to_id}

        # Map typed presentation actions into Discord ActionRow buttons (Invariant T35-06)
        actions = message.metadata.get("actions", [])
        if actions:
            components = []
            for action in actions:
                is_danger = (
                    action.get("style") == "danger"
                    or "reject" in action.get("action_id", "").lower()
                )
                components.append(
                    {
                        "type": 2,  # Button
                        "style": 4 if is_danger else 3,  # Danger (red) vs Success (green)
                        "label": action.get("label", action.get("text", "Action")),
                        "custom_id": action.get("action_id", action.get("value", "")),
                    }
                )
            payload["components"] = [{"type": 1, "components": components}]  # Type 1: ActionRow

        return payload

    def send_to_provider(
        self, native_payload: dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Send payload to Discord Bot API."""
        if self._provider_send_fn is not None:
            return self._provider_send_fn(native_payload)
        # Default loopback simulation returning success with mock Discord snowflake ID
        mock_id = f"11{uuid.uuid4().int % 10000000000000000:016d}"
        return (True, mock_id, None)


__all__ = ["DiscordTransportAdapter"]
