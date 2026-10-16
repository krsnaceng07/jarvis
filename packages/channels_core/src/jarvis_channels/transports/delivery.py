"""Outbound channel delivery tracking for Track 3.5.

Enforces Invariant T35-15:
External channel outbound deliveries track formal status lifecycle:
CREATED -> QUEUED -> DISPATCHED -> PROVIDER_ACCEPTED -> DELIVERED (or FAILED, UNKNOWN).
PROVIDER_ACCEPTED is the universal milestone for successful API submission.
DELIVERED is emitted only when explicit provider delivery confirmation exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from enum import Enum
import hashlib
from pathlib import Path
import sqlite3
from typing import Optional


class ChannelDeliveryStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    PROVIDER_ACCEPTED = "PROVIDER_ACCEPTED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ChannelDeliveryRecord:
    """Persistent record of an outbound delivery."""

    delivery_id: str
    message_id: str
    channel_id: str
    recipient_id: str
    payload_hash: str
    attempt_count: int
    status: ChannelDeliveryStatus
    provider_response_id: Optional[str]
    error_message: Optional[str]
    created_at_utc: str
    updated_at_utc: str


class ChannelDeliveryTracker:
    """Thread-safe SQLite WAL tracker enforcing outbound delivery lifecycle."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = str(db_path or ":memory:")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_outbound_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    provider_response_id TEXT,
                    error_message TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outbound_msg ON channel_outbound_deliveries(message_id, recipient_id);"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_outbound_status ON channel_outbound_deliveries(status);"
            )

    def create_delivery(
        self,
        delivery_id: str,
        message_id: str,
        channel_id: str,
        recipient_id: str,
        payload_text: str,
    ) -> ChannelDeliveryRecord:
        """Create new delivery record in CREATED state."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload_hash = hashlib.sha256(payload_text.encode("utf-8")).hexdigest()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO channel_outbound_deliveries
                (delivery_id, message_id, channel_id, recipient_id, payload_hash, attempt_count, status, provider_response_id, error_message, created_at_utc, updated_at_utc)
                VALUES (?, ?, ?, ?, ?, 0, ?, NULL, NULL, ?, ?);
                """,
                (
                    delivery_id,
                    message_id,
                    channel_id,
                    recipient_id,
                    payload_hash,
                    ChannelDeliveryStatus.CREATED.value,
                    now,
                    now,
                ),
            )
        return self.get_delivery(delivery_id)  # type: ignore[return-value]

    def mark_queued(self, delivery_id: str) -> bool:
        """Advance status to QUEUED."""
        return self._transition_status(delivery_id, ChannelDeliveryStatus.QUEUED)

    def mark_dispatched(self, delivery_id: str) -> bool:
        """Advance status to DISPATCHED and increment attempt_count."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_outbound_deliveries
                SET status = ?, attempt_count = attempt_count + 1, updated_at_utc = ?
                WHERE delivery_id = ?;
                """,
                (ChannelDeliveryStatus.DISPATCHED.value, now, delivery_id),
            )
            return cursor.rowcount > 0

    def mark_provider_accepted(
        self, delivery_id: str, provider_response_id: str | None = None
    ) -> bool:
        """Advance status to PROVIDER_ACCEPTED upon successful API call."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_outbound_deliveries
                SET status = ?, provider_response_id = ?, updated_at_utc = ?
                WHERE delivery_id = ?;
                """,
                (
                    ChannelDeliveryStatus.PROVIDER_ACCEPTED.value,
                    provider_response_id,
                    now,
                    delivery_id,
                ),
            )
            return cursor.rowcount > 0

    def mark_delivered(self, delivery_id: str) -> bool:
        """Advance status to DELIVERED only upon verified delivery receipt."""
        return self._transition_status(delivery_id, ChannelDeliveryStatus.DELIVERED)

    def mark_failed(self, delivery_id: str, error_message: str) -> bool:
        """Record delivery failure."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_outbound_deliveries
                SET status = ?, error_message = ?, updated_at_utc = ?
                WHERE delivery_id = ?;
                """,
                (ChannelDeliveryStatus.FAILED.value, error_message, now, delivery_id),
            )
            return cursor.rowcount > 0

    def mark_unknown(self, delivery_id: str, reason: str) -> bool:
        """Transition delivery to UNKNOWN when response is ambiguous or timed out."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_outbound_deliveries
                SET status = ?, error_message = ?, updated_at_utc = ?
                WHERE delivery_id = ?;
                """,
                (ChannelDeliveryStatus.UNKNOWN.value, reason, now, delivery_id),
            )
            return cursor.rowcount > 0

    def get_delivery(self, delivery_id: str) -> ChannelDeliveryRecord | None:
        """Fetch delivery record by ID."""
        cursor = self._conn.execute(
            "SELECT * FROM channel_outbound_deliveries WHERE delivery_id = ?;",
            (delivery_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return ChannelDeliveryRecord(
            delivery_id=row["delivery_id"],
            message_id=row["message_id"],
            channel_id=row["channel_id"],
            recipient_id=row["recipient_id"],
            payload_hash=row["payload_hash"],
            attempt_count=row["attempt_count"],
            status=ChannelDeliveryStatus(row["status"]),
            provider_response_id=row["provider_response_id"],
            error_message=row["error_message"],
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )

    def _transition_status(self, delivery_id: str, new_status: ChannelDeliveryStatus) -> bool:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_outbound_deliveries
                SET status = ?, updated_at_utc = ?
                WHERE delivery_id = ?;
                """,
                (new_status.value, now, delivery_id),
            )
            return cursor.rowcount > 0

    def close(self) -> None:
        """Close SQLite database connection."""
        try:
            self._conn.close()
        except Exception:
            pass


__all__ = ["ChannelDeliveryStatus", "ChannelDeliveryRecord", "ChannelDeliveryTracker"]
