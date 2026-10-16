"""Outbound channel router and transport adapter dispatch for Track 3.4.

Enforces Invariant T34-05: Outbound messages route strictly according to ResponseRoute.
Enforces Invariant T34-19: Outbound channel delivery tracks explicit delivery states.
"""

from __future__ import annotations

from typing import Any, Protocol
import uuid

from jarvis_agent.gateway.delivery_ledger import DeliveryLedger, DeliveryRecord
from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import DeliveryStatus
from jarvis_agent.orchestration.models.response_route import ResponseRoute


class ChannelAdapter(Protocol):
    """Transport adapter protocol for external channels."""

    def deliver_message(
        self,
        route: ResponseRoute,
        payload: dict[str, Any],
        delivery_id: str,
    ) -> bool: ...


class ChannelRouter:
    """Routes outbound messages to registered channel adapters with idempotency protection."""

    def __init__(self, delivery_ledger: DeliveryLedger) -> None:
        self.delivery_ledger = delivery_ledger
        self._adapters: dict[str, ChannelAdapter] = {}

    def register_adapter(self, channel: str, adapter: ChannelAdapter) -> None:
        """Register adapter for a specific channel name (e.g. desktop, telegram, discord)."""
        self._adapters[channel] = adapter

    def dispatch_outbound(
        self,
        route: ResponseRoute,
        message_id: str,
        payload: dict[str, Any],
    ) -> DeliveryRecord:
        """Dispatch outbound message to the target channel adapter."""
        delivery_id = f"deliv_{uuid.uuid4().hex[:10]}"
        recipient = route.user_id

        # Check delivery ledger
        is_new, record = self.delivery_ledger.record_outbound(
            delivery_id=delivery_id,
            message_id=message_id,
            channel=route.channel,
            recipient_id=recipient,
            payload=payload,
        )

        # Idempotent replay: if already delivered, return existing record
        if not is_new and record.status == DeliveryStatus.DELIVERED:
            return record

        adapter = self._adapters.get(route.channel)
        if not adapter:
            self.delivery_ledger.update_status(record.delivery_id, DeliveryStatus.FAILED)
            raise GatewayException(
                code=GatewayErrorCode.INVALID_PARAMS,
                message=f"No transport adapter registered for channel '{route.channel}'.",
            )

        # Update status to DISPATCHED
        self.delivery_ledger.update_status(record.delivery_id, DeliveryStatus.DISPATCHED)

        try:
            success = adapter.deliver_message(route, payload, record.delivery_id)
            if success:
                self.delivery_ledger.update_status(record.delivery_id, DeliveryStatus.DELIVERED)
                return DeliveryRecord(
                    delivery_id=record.delivery_id,
                    message_id=record.message_id,
                    channel=record.channel,
                    recipient_id=record.recipient_id,
                    payload_hash=record.payload_hash,
                    attempt_count=record.attempt_count,
                    status=DeliveryStatus.DELIVERED,
                    created_at_utc=record.created_at_utc,
                    updated_at_utc=record.updated_at_utc,
                )
            else:
                self.delivery_ledger.update_status(record.delivery_id, DeliveryStatus.FAILED)
                return DeliveryRecord(
                    delivery_id=record.delivery_id,
                    message_id=record.message_id,
                    channel=record.channel,
                    recipient_id=record.recipient_id,
                    payload_hash=record.payload_hash,
                    attempt_count=record.attempt_count,
                    status=DeliveryStatus.FAILED,
                    created_at_utc=record.created_at_utc,
                    updated_at_utc=record.updated_at_utc,
                )
        except Exception:
            self.delivery_ledger.update_status(record.delivery_id, DeliveryStatus.FAILED)
            raise


__all__ = ["ChannelAdapter", "ChannelRouter"]
