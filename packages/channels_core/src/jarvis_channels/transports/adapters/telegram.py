"""Telegram server-side channel transport adapter for Track 3.5.

Enforces:
- Invariant T35-04: Server-side channel transport adapter.
- Invariant T35-05: Server-authoritative route triple (telegram, user_id, thread_id).
- Invariant T35-06: Inline keyboard action buttons for approval/decision turns.
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


class TelegramTransportAdapter(BaseChannelTransport):
    """Server-side transport adapter for Telegram bot integration."""

    def __init__(
        self,
        deduplicator: ChannelInboundDeduplicator,
        tracker: ChannelDeliveryTracker,
        provider_send_fn: Optional[
            Callable[[dict[str, Any]], tuple[bool, Optional[str], Optional[str]]]
        ] = None,
    ) -> None:
        super().__init__(
            channel_id="telegram",
            deduplicator=deduplicator,
            tracker=tracker,
        )
        self._provider_send_fn = provider_send_fn

    def parse_inbound_raw(
        self,
        raw_event: dict[str, Any],
    ) -> tuple[str, str, Optional[str], str, dict[str, Any]] | None:
        """Parse Telegram Update into canonical fields."""
        msg = raw_event.get("message") or raw_event.get("edited_message")
        if not msg:
            # Check callback_query (inline button clicks)
            cb = raw_event.get("callback_query")
            if cb:
                msg_id = str(cb.get("id"))
                from_user = cb.get("from", {})
                user_id = str(from_user.get("id", "unknown"))
                orig_msg = cb.get("message", {})
                thread_id = (
                    str(orig_msg.get("message_thread_id"))
                    if "message_thread_id" in orig_msg
                    else None
                )
                data = cb.get("data", "")
                return (msg_id, user_id, thread_id, data, {"callback_query_id": cb.get("id")})
            return None

        msg_id = str(msg.get("message_id"))
        from_user = msg.get("from", {})
        user_id = str(from_user.get("id", "unknown"))
        thread_id = str(msg.get("message_thread_id")) if "message_thread_id" in msg else None
        text = msg.get("text", "")
        return (msg_id, user_id, thread_id, text, {})

    def format_native_outbound(self, message: OutboundMessage) -> dict[str, Any]:
        """Format OutboundMessage into Telegram sendMessage payload with inline keyboard."""
        payload: dict[str, Any] = {
            "chat_id": message.conversation_id,
            "text": message.text,
            "parse_mode": message.metadata.get("parse_mode", "Markdown"),
        }
        if message.reply_to_id:
            payload["reply_to_message_id"] = message.reply_to_id

        # Map typed presentation actions into Telegram inline_keyboard (Invariant T35-06)
        actions = message.metadata.get("actions", [])
        if actions:
            buttons = []
            for action in actions:
                buttons.append(
                    {
                        "text": action.get("label", action.get("text", "Action")),
                        "callback_data": action.get("action_id", action.get("value", "")),
                    }
                )
            payload["reply_markup"] = {"inline_keyboard": [buttons]}

        return payload

    def send_to_provider(
        self, native_payload: dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Send payload to Telegram Bot API."""
        if self._provider_send_fn is not None:
            return self._provider_send_fn(native_payload)
        # Default loopback simulation returning success with mock Telegram message_id
        mock_id = f"tg_msg_{uuid.uuid4().hex[:10]}"
        return (True, mock_id, None)


__all__ = ["TelegramTransportAdapter"]
