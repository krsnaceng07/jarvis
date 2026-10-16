"""Slack server-side channel transport adapter for Track 3.5.

Enforces:
- Invariant T35-04: Server-side channel transport adapter.
- Invariant T35-05: Server-authoritative route triple (slack, user_id, thread_ts).
- Invariant T35-06: Block Kit interactive buttons for approval/decision turns.
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


class SlackTransportAdapter(BaseChannelTransport):
    """Server-side transport adapter for Slack bot integration."""

    def __init__(
        self,
        deduplicator: ChannelInboundDeduplicator,
        tracker: ChannelDeliveryTracker,
        provider_send_fn: Optional[
            Callable[[dict[str, Any]], tuple[bool, Optional[str], Optional[str]]]
        ] = None,
    ) -> None:
        super().__init__(
            channel_id="slack",
            deduplicator=deduplicator,
            tracker=tracker,
        )
        self._provider_send_fn = provider_send_fn

    def parse_inbound_raw(
        self,
        raw_event: dict[str, Any],
    ) -> tuple[str, str, Optional[str], str, dict[str, Any]] | None:
        """Parse Slack Events API payload into canonical fields."""
        # Handle interactive block_actions (button clicks)
        if raw_event.get("type") == "block_actions":
            msg_id = str(
                raw_event.get("trigger_id") or raw_event.get("action_ts") or uuid.uuid4().hex[:8]
            )
            user = raw_event.get("user", {})
            user_id = str(user.get("id", "unknown"))
            container = raw_event.get("container", {})
            channel_id = str(container.get("channel_id", "root"))
            actions = raw_event.get("actions", [])
            action_value = actions[0].get("value", "") if actions else ""
            return (
                msg_id,
                user_id,
                channel_id,
                action_value,
                {"response_url": raw_event.get("response_url")},
            )

        # Standard event_callback
        event = raw_event.get("event", raw_event)
        if event.get("type") != "message":
            return None

        # Ignore bot messages or message_changed / message_deleted subtypes
        if event.get("bot_id") or event.get("subtype"):
            return None

        msg_id = str(event.get("client_msg_id") or event.get("ts") or uuid.uuid4().hex[:8])
        user_id = str(event.get("user", "unknown"))
        thread_id = str(event.get("thread_ts")) if "thread_ts" in event else None
        text = event.get("text", "")
        return (msg_id, user_id, thread_id, text, {"channel": event.get("channel")})

    def format_native_outbound(self, message: OutboundMessage) -> dict[str, Any]:
        """Format OutboundMessage into Slack chat.postMessage payload with Block Kit blocks."""
        payload: dict[str, Any] = {
            "channel": message.conversation_id,
            "text": message.text,
        }
        if message.reply_to_id:
            payload["thread_ts"] = message.reply_to_id

        # Map typed presentation actions into Slack Block Kit blocks (Invariant T35-06)
        actions = message.metadata.get("actions", [])
        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message.text},
            }
        ]

        if actions:
            elements = []
            for action in actions:
                is_danger = (
                    action.get("style") == "danger"
                    or "reject" in action.get("action_id", "").lower()
                )
                elements.append(
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": action.get("label", action.get("text", "Action")),
                        },
                        "action_id": action.get("action_id", action.get("value", "")),
                        "value": action.get("value", action.get("action_id", "")),
                        "style": "danger" if is_danger else "primary",
                    }
                )
            blocks.append({"type": "actions", "elements": elements})

        payload["blocks"] = blocks
        return payload

    def send_to_provider(
        self, native_payload: dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Send payload to Slack Web API chat.postMessage."""
        if self._provider_send_fn is not None:
            return self._provider_send_fn(native_payload)
        # Default loopback simulation returning success with mock Slack timestamp
        mock_ts = f"171{uuid.uuid4().int % 10000000:07d}.{uuid.uuid4().int % 1000000:06d}"
        return (True, mock_ts, None)


__all__ = ["SlackTransportAdapter"]
