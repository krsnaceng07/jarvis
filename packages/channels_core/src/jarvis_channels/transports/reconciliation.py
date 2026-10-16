"""Delivery reconciliation for timed-out outbound channel dispatches.

Enforces Invariant T35-15:
Outbound dispatches that encounter socket timeouts or crashes transition to UNKNOWN
rather than silently re-transmitting, avoiding duplicate messages to real users.
"""

from __future__ import annotations

import datetime
from typing import Callable, Optional

from jarvis_channels.transports.delivery import (
    ChannelDeliveryStatus,
    ChannelDeliveryTracker,
)


class ChannelDeliveryReconciler:
    """Reconciles ambiguous or timed-out outbound channel dispatches."""

    def __init__(
        self,
        tracker: ChannelDeliveryTracker,
        dispatch_timeout_seconds: float = 30.0,
    ) -> None:
        self.tracker = tracker
        self.dispatch_timeout_seconds = dispatch_timeout_seconds

    def reconcile_stale_dispatches(self) -> list[str]:
        """Find deliveries stuck in DISPATCHED past timeout and transition to UNKNOWN."""
        now = datetime.datetime.now(datetime.timezone.utc)
        reconciled_ids: list[str] = []

        with self.tracker._conn:
            cursor = self.tracker._conn.execute(
                "SELECT delivery_id, updated_at_utc FROM channel_outbound_deliveries WHERE status = ?;",
                (ChannelDeliveryStatus.DISPATCHED.value,),
            )
            rows = cursor.fetchall()
            for row in rows:
                deliv_id = row["delivery_id"]
                updated_at_str = row["updated_at_utc"]
                try:
                    updated_at = datetime.datetime.fromisoformat(updated_at_str)
                    age_seconds = (now - updated_at).total_seconds()
                    if age_seconds >= self.dispatch_timeout_seconds:
                        self.tracker.mark_unknown(
                            delivery_id=deliv_id,
                            reason=f"Dispatch timed out after {age_seconds:.1f}s without provider ack.",
                        )
                        reconciled_ids.append(deliv_id)
                except Exception:
                    pass

        return reconciled_ids

    def can_safely_resend(
        self,
        delivery_id: str,
        provider_verifier: Optional[Callable[[str], bool]] = None,
    ) -> bool:
        """Check if an outbound message can be safely resent.

        Strictly returns False if status is PROVIDER_ACCEPTED or DELIVERED.
        If status is UNKNOWN, requires external provider verifier confirming non-receipt.
        """
        record = self.tracker.get_delivery(delivery_id)
        if record is None:
            return False

        if record.status in (
            ChannelDeliveryStatus.PROVIDER_ACCEPTED,
            ChannelDeliveryStatus.DELIVERED,
        ):
            return False

        if record.status == ChannelDeliveryStatus.FAILED:
            return True

        if record.status == ChannelDeliveryStatus.UNKNOWN:
            if provider_verifier is not None:
                # Verifier returns True if provider confirms message was NOT accepted
                return provider_verifier(delivery_id)
            return False

        return False


__all__ = ["ChannelDeliveryReconciler"]
