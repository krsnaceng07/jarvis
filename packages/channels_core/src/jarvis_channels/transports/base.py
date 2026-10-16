"""Base channel transport adapter for Track 3.5.

Enforces:
- Invariant T35-04: External channels run server-side, mapping webhook/polling to internal protocol.
- Invariant T35-05: Synthesizes server-authoritative route triples (channel_id, user_id, thread_id).
- Invariant T35-06: Typed presentation actions rather than raw string inference.
- Invariant T35-15: 6-state outbound delivery tracking (CREATED -> QUEUED -> DISPATCHED -> PROVIDER_ACCEPTED -> DELIVERED).
- Invariant T35-16: SQLite WAL atomic claim deduplication for inbound events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import json
from typing import Any, Optional
import uuid

from jarvis_channels.transports.deduplication import ChannelInboundDeduplicator
from jarvis_channels.transports.delivery import (
    ChannelDeliveryRecord,
    ChannelDeliveryTracker,
)
from jarvis_channels.transports.identity import synthesize_route_triple
from jarvis_channels.types import InboundMessage, OutboundMessage


class BaseChannelTransport(ABC):
    """Abstract base class for server-side external channel transports."""

    def __init__(
        self,
        channel_id: str,
        deduplicator: ChannelInboundDeduplicator,
        tracker: ChannelDeliveryTracker,
    ) -> None:
        self.channel_id = channel_id
        self.deduplicator = deduplicator
        self.tracker = tracker

    @abstractmethod
    def parse_inbound_raw(
        self,
        raw_event: dict[str, Any],
    ) -> tuple[str, str, Optional[str], str, dict[str, Any]] | None:
        """Parse raw external payload into:
        (external_message_id, external_user_id, external_thread_id, text, metadata).

        Returns None if the raw event is not a user message (e.g. system noise).
        """
        ...

    @abstractmethod
    def format_native_outbound(self, message: OutboundMessage) -> dict[str, Any]:
        """Format OutboundMessage into channel-native API request body.

        Enforces Invariant T35-06: Typed presentation actions mapped into native widgets.
        """
        ...

    @abstractmethod
    def send_to_provider(
        self, native_payload: dict[str, Any]
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Perform API call to external platform.

        Returns (success: bool, provider_message_id: str | None, error_message: str | None).
        """
        ...

    def handle_inbound(self, raw_event: dict[str, Any]) -> InboundMessage | None:
        """Process inbound event with atomic deduplication and route synthesis."""
        parsed = self.parse_inbound_raw(raw_event)
        if parsed is None:
            return None

        msg_id, user_id, thread_id, text, metadata = parsed

        # Invariant T35-16: Atomic claim in SQLite WAL
        payload_hash = hashlib.sha256(
            json.dumps(raw_event, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        claimed = self.deduplicator.atomic_claim(
            channel_id=self.channel_id,
            message_id=msg_id,
            payload_hash=payload_hash,
        )
        if not claimed:
            # Duplicate or concurrent arrival dropped
            return None

        self.deduplicator.mark_processing(self.channel_id, msg_id)

        # Invariant T35-05: Route triple synthesis
        route = synthesize_route_triple(
            channel_id=self.channel_id,
            external_user_id=user_id,
            external_thread_id=thread_id,
        )

        return InboundMessage(
            channel_id=self.channel_id,
            conversation_id=route.session_key,
            sender_id=user_id,
            text=text,
            raw=raw_event,
            peer_id=user_id,
            thread_id=thread_id,
        )

    def dispatch_outbound(self, message: OutboundMessage) -> ChannelDeliveryRecord:
        """Dispatch outbound message through 6-state delivery tracker."""
        delivery_id = f"del_{uuid.uuid4().hex[:12]}"
        msg_id = message.reply_to_id or f"msg_{uuid.uuid4().hex[:8]}"

        # Step 1: CREATED
        record = self.tracker.create_delivery(
            delivery_id=delivery_id,
            message_id=msg_id,
            channel_id=self.channel_id,
            recipient_id=message.conversation_id,
            payload_text=message.text,
        )

        # Step 2: QUEUED
        self.tracker.mark_queued(delivery_id)

        # Step 3: Format native payload (Invariant T35-06)
        native_body = self.format_native_outbound(message)

        # Step 4: DISPATCHED
        self.tracker.mark_dispatched(delivery_id)

        # Step 5: Send to provider API
        success, provider_id, error = self.send_to_provider(native_body)

        if success:
            # Step 6: PROVIDER_ACCEPTED (universal milestone, Invariant T35-15)
            self.tracker.mark_provider_accepted(delivery_id, provider_response_id=provider_id)
        else:
            self.tracker.mark_failed(delivery_id, error_message=error or "Provider send failed")

        return self.tracker.get_delivery(delivery_id) or record

    def confirm_delivered(self, delivery_id: str) -> bool:
        """Mark delivery as confirmed DELIVERED via explicit receipt proof."""
        return self.tracker.mark_delivered(delivery_id)

    def mark_inbound_completed(self, message_id: str) -> bool:
        """Mark inbound message processing as COMPLETED."""
        return self.deduplicator.mark_completed(self.channel_id, message_id)

    def mark_inbound_failed(self, message_id: str, error: str) -> bool:
        """Mark inbound message processing as FAILED."""
        return self.deduplicator.mark_failed(self.channel_id, message_id, error)


__all__ = ["BaseChannelTransport"]
