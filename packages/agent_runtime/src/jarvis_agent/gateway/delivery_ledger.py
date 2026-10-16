"""Outbound channel delivery ledger for Track 3.4.

Enforces Invariant T34-19: Outbound channel delivery tracks formal delivery states
(CREATED -> QUEUED -> DISPATCHED -> TRANSPORT_ACCEPTED -> DELIVERED / FAILED)
and guarantees outbound delivery idempotency.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from jarvis_agent.gateway.models import DeliveryStatus


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    """Persistent record of an outbound channel delivery."""

    delivery_id: str
    message_id: str
    channel: str
    recipient_id: str
    payload_hash: str
    attempt_count: int
    status: DeliveryStatus
    created_at_utc: str
    updated_at_utc: str


class DeliveryLedger:
    """Thread-safe SQLite WAL ledger tracking delivery state and preventing duplicate channel messages."""

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
                CREATE TABLE IF NOT EXISTS gateway_deliveries (
                    delivery_id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gw_deliv_msg ON gateway_deliveries(message_id, recipient_id);"
            )

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    @staticmethod
    def hash_payload(payload: Any) -> str:
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def record_outbound(
        self,
        delivery_id: str,
        message_id: str,
        channel: str,
        recipient_id: str,
        payload: Any,
    ) -> tuple[bool, DeliveryRecord]:
        """Record outbound message intent; returns (is_new, record).

        If (message_id, recipient_id) already exists and is DELIVERED, returns (False, record).
        """
        payload_hash = self.hash_payload(payload)
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self._conn:
            cur = self._conn.execute(
                """
                SELECT * FROM gateway_deliveries
                WHERE message_id = ? AND recipient_id = ?;
                """,
                (message_id, recipient_id),
            )
            row = cur.fetchone()
            if row:
                rec = self._row_to_record(row)
                if rec.status == DeliveryStatus.DELIVERED:
                    return False, rec

            self._conn.execute(
                """
                INSERT INTO gateway_deliveries (
                    delivery_id, message_id, channel, recipient_id, payload_hash,
                    attempt_count, status, created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(delivery_id) DO UPDATE SET
                    attempt_count = attempt_count + 1,
                    updated_at_utc = excluded.updated_at_utc;
                """,
                (
                    delivery_id,
                    message_id,
                    channel,
                    recipient_id,
                    payload_hash,
                    DeliveryStatus.QUEUED.value,
                    now_str,
                    now_str,
                ),
            )
            cur2 = self._conn.execute(
                "SELECT * FROM gateway_deliveries WHERE delivery_id = ?;", (delivery_id,)
            )
            return True, self._row_to_record(cur2.fetchone())

    def update_status(self, delivery_id: str, status: DeliveryStatus) -> None:
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                "UPDATE gateway_deliveries SET status = ?, updated_at_utc = ? WHERE delivery_id = ?;",
                (status.value, now_str, delivery_id),
            )

    def _row_to_record(self, row: Any) -> DeliveryRecord:
        return DeliveryRecord(
            delivery_id=row["delivery_id"],
            message_id=row["message_id"],
            channel=row["channel"],
            recipient_id=row["recipient_id"],
            payload_hash=row["payload_hash"],
            attempt_count=int(row["attempt_count"]),
            status=DeliveryStatus(row["status"]),
            created_at_utc=row["created_at_utc"],
            updated_at_utc=row["updated_at_utc"],
        )


__all__ = ["DeliveryRecord", "DeliveryLedger"]
