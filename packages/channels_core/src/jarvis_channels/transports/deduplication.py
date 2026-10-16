"""Inbound channel event deduplication for Track 3.5.

Enforces Invariant T35-16:
Inbound channel event deduplication uses an atomic claim pattern
(RECEIVED -> CLAIMED -> PROCESSING -> COMPLETED / FAILED) in SQLite WAL to prevent
concurrent worker races or duplicate execution.
"""

from __future__ import annotations

import datetime
from enum import Enum
from pathlib import Path
import sqlite3


class InboundClaimState(str, Enum):
    RECEIVED = "RECEIVED"
    CLAIMED = "CLAIMED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChannelInboundDeduplicator:
    """Thread-safe SQLite WAL deduplicator enforcing atomic message claims."""

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
                CREATE TABLE IF NOT EXISTS channel_inbound_claims (
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    state TEXT NOT NULL,
                    error_message TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (channel_id, message_id)
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_inbound_claims_state ON channel_inbound_claims(state);"
            )

    def atomic_claim(
        self,
        channel_id: str,
        message_id: str,
        payload_hash: str,
    ) -> bool:
        """Atomically claim an inbound message.

        Returns True if the message was successfully claimed (first arrival),
        or False if already claimed/processing/completed.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            with self._conn:
                cursor = self._conn.cursor()
                cursor.execute("BEGIN IMMEDIATE;")
                # Check existing claim
                cursor.execute(
                    "SELECT state FROM channel_inbound_claims WHERE channel_id = ? AND message_id = ?;",
                    (channel_id, message_id),
                )
                row = cursor.fetchone()
                if row is not None:
                    # Already exists
                    return False

                # Insert as CLAIMED
                cursor.execute(
                    """
                    INSERT INTO channel_inbound_claims
                    (channel_id, message_id, payload_hash, state, created_at_utc, updated_at_utc)
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        channel_id,
                        message_id,
                        payload_hash,
                        InboundClaimState.CLAIMED.value,
                        now,
                        now,
                    ),
                )
                return True
        except sqlite3.IntegrityError:
            return False

    def mark_processing(self, channel_id: str, message_id: str) -> bool:
        """Transition claim from CLAIMED to PROCESSING."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_inbound_claims
                SET state = ?, updated_at_utc = ?
                WHERE channel_id = ? AND message_id = ? AND state = ?;
                """,
                (
                    InboundClaimState.PROCESSING.value,
                    now,
                    channel_id,
                    message_id,
                    InboundClaimState.CLAIMED.value,
                ),
            )
            return cursor.rowcount > 0

    def mark_completed(self, channel_id: str, message_id: str) -> bool:
        """Mark inbound processing as COMPLETED."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_inbound_claims
                SET state = ?, updated_at_utc = ?
                WHERE channel_id = ? AND message_id = ?;
                """,
                (
                    InboundClaimState.COMPLETED.value,
                    now,
                    channel_id,
                    message_id,
                ),
            )
            return cursor.rowcount > 0

    def mark_failed(self, channel_id: str, message_id: str, error_message: str) -> bool:
        """Mark inbound processing as FAILED."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            cursor = self._conn.execute(
                """
                UPDATE channel_inbound_claims
                SET state = ?, error_message = ?, updated_at_utc = ?
                WHERE channel_id = ? AND message_id = ?;
                """,
                (
                    InboundClaimState.FAILED.value,
                    error_message,
                    now,
                    channel_id,
                    message_id,
                ),
            )
            return cursor.rowcount > 0

    def get_claim_state(self, channel_id: str, message_id: str) -> InboundClaimState | None:
        """Return the current claim state of an inbound message."""
        cursor = self._conn.execute(
            "SELECT state FROM channel_inbound_claims WHERE channel_id = ? AND message_id = ?;",
            (channel_id, message_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return InboundClaimState(row["state"])

    def close(self) -> None:
        """Close SQLite database connection."""
        try:
            self._conn.close()
        except Exception:
            pass


__all__ = ["InboundClaimState", "ChannelInboundDeduplicator"]
