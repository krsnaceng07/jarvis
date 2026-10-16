"""Durable event consumer and cursor tracking for Track 3.4.

Enforces Invariant T34-02: Committed EventStore records are authoritative;
notifications are advisory wake-up signals.
Enforces Invariant T34-11: Gateway event consumption maintains a durable cursor
and recovers missed committed events post-restart.
"""

from __future__ import annotations

from collections import deque
import datetime
import json
from pathlib import Path
import sqlite3
from typing import Callable

from jarvis_agent.gateway.models import (
    EnrichedGatewayEvent,
    EventCategory,
    SequenceTriad,
)
from jarvis_agent.orchestration.state.event_store import EventStore


class GatewayEventCursorStore:
    """SQLite WAL store persisting consumer cursor progress."""

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
                CREATE TABLE IF NOT EXISTS gateway_consumer_cursors (
                    consumer_id TEXT PRIMARY KEY,
                    journal_id TEXT NOT NULL,
                    last_committed_global_seq INTEGER NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                """
            )

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def get_cursor(self, consumer_id: str, journal_id: str = "default") -> int:
        """Get last committed global sequence number for consumer, or 0 if none."""
        with self._conn:
            cur = self._conn.execute(
                "SELECT last_committed_global_seq FROM gateway_consumer_cursors WHERE consumer_id = ? AND journal_id = ?",
                (consumer_id, journal_id),
            )
            row = cur.fetchone()
            return int(row["last_committed_global_seq"]) if row else 0

    def save_cursor(self, consumer_id: str, journal_id: str, global_seq: int) -> None:
        """Atomically persist consumer progress."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO gateway_consumer_cursors (consumer_id, journal_id, last_committed_global_seq, updated_at_utc)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(consumer_id) DO UPDATE SET
                    journal_id = excluded.journal_id,
                    last_committed_global_seq = excluded.last_committed_global_seq,
                    updated_at_utc = excluded.updated_at_utc;
                """,
                (consumer_id, journal_id, global_seq, now_str),
            )


class GatewayEventConsumer:
    """Polls authoritative EventStore using durable cursor and dispatches to listeners."""

    def __init__(
        self,
        event_store: EventStore,
        cursor_store: GatewayEventCursorStore,
        consumer_id: str = "gateway_main",
        journal_id: str = "default",
        dedupe_cache_size: int = 10_000,
    ) -> None:
        self.event_store = event_store
        self.cursor_store = cursor_store
        self.consumer_id = consumer_id
        self.journal_id = journal_id
        self._listeners: list[Callable[[EnrichedGatewayEvent], None]] = []
        self._seen_event_ids: deque[str] = deque(maxlen=dedupe_cache_size)
        self._seen_set: set[str] = set()

    def register_listener(self, listener: Callable[[EnrichedGatewayEvent], None]) -> None:
        self._listeners.append(listener)

    def notify_committed(self) -> int:
        """Advisory wake-up signal triggered when events are committed to EventStore."""
        return self.poll_committed_events()

    def poll_committed_events(self, limit: int = 500) -> int:
        """Poll and dispatch new committed events from last durable cursor.

        Returns number of dispatched new events.
        """
        last_seq = self.cursor_store.get_cursor(self.consumer_id, self.journal_id)
        cur = self.event_store._conn.cursor()

        cur.execute(
            """
            SELECT rowid, event_id, task_id, conversation_id, event_type,
                   timestamp_utc, sequence_number, payload_json,
                   causation_event_id, correlation_id
            FROM orchestration_events
            WHERE rowid > ?
            ORDER BY rowid ASC
            LIMIT ?;
            """,
            (last_seq, limit),
        )
        rows = cur.fetchall()
        if not rows:
            return 0

        dispatched_count = 0
        new_cursor = last_seq

        for r in rows:
            global_seq = int(r[0])
            event_id = str(r[1])
            # r[2] is task_id
            event_type = str(r[4])
            ts_utc = str(r[5])
            agg_version = int(r[6])
            payload = json.loads(r[7])
            causation_id = r[8]
            correlation_id = r[9]

            new_cursor = max(new_cursor, global_seq)

            # Deduplication
            if event_id in self._seen_set:
                continue

            if len(self._seen_event_ids) == self._seen_event_ids.maxlen:
                evicted = self._seen_event_ids.popleft()
                self._seen_set.discard(evicted)
            self._seen_event_ids.append(event_id)
            self._seen_set.add(event_id)

            category = (
                EventCategory.TELEMETRY
                if "chunk" in event_type or "progress" in event_type
                else EventCategory.AUTHORITATIVE
            )

            # Build enriched event
            enriched = EnrichedGatewayEvent.create(
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                category=category,
                sequence=SequenceTriad(
                    global_seq=global_seq,
                    aggregate_version=agg_version,
                    connection_seq=0,  # Bound per connection during streaming
                ),
                timestamp_utc=ts_utc,
                causation_id=causation_id,
                correlation_id=correlation_id,
            )

            for listener in self._listeners:
                try:
                    listener(enriched)
                except Exception:
                    pass

            dispatched_count += 1

        # Atomically advance durable cursor
        self.cursor_store.save_cursor(self.consumer_id, self.journal_id, new_cursor)
        return dispatched_count


__all__ = ["GatewayEventCursorStore", "GatewayEventConsumer"]
