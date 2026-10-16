"""Append-only SQLite/WAL backed event journal for orchestration state sourcing."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from jarvis_agent.orchestration.state.event import DomainEvent, EventType


class EventStore:
    """Append-only persistent event journal backed by SQLite WAL."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._db_path = ":memory:"
        else:
            self._db_path = str(db_path)
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initialize WAL mode and event schema."""
        cursor = self._conn.cursor()
        if self._db_path != ":memory:":
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orchestration_events (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                sequence_number INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                causation_event_id TEXT,
                correlation_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_task_seq 
            ON orchestration_events (task_id, sequence_number);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_conversation 
            ON orchestration_events (conversation_id);
        """)
        self._conn.commit()

    def append(self, event: DomainEvent) -> None:
        """Append a single domain event into the journal."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO orchestration_events (
                event_id, task_id, conversation_id, event_type,
                timestamp_utc, sequence_number, payload_json,
                causation_event_id, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                event.event_id,
                event.task_id,
                event.conversation_id,
                event.event_type.value,
                event.timestamp_utc,
                event.sequence_number,
                json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
                event.causation_event_id,
                event.correlation_id,
            ),
        )
        self._conn.commit()

    def append_batch(self, events: list[DomainEvent]) -> None:
        """Append a batch of domain events within a single transaction."""
        if not events:
            return
        cursor = self._conn.cursor()
        cursor.executemany(
            """
            INSERT INTO orchestration_events (
                event_id, task_id, conversation_id, event_type,
                timestamp_utc, sequence_number, payload_json,
                causation_event_id, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            [
                (
                    e.event_id,
                    e.task_id,
                    e.conversation_id,
                    e.event_type.value,
                    e.timestamp_utc,
                    e.sequence_number,
                    json.dumps(e.payload, sort_keys=True, separators=(",", ":")),
                    e.causation_event_id,
                    e.correlation_id,
                )
                for e in events
            ],
        )
        self._conn.commit()

    def get_events_for_task(self, task_id: str, after_sequence: int = 0) -> list[DomainEvent]:
        """Fetch all events for a given task, optionally starting after sequence_number."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT event_id, task_id, conversation_id, event_type,
                   timestamp_utc, sequence_number, payload_json,
                   causation_event_id, correlation_id
            FROM orchestration_events
            WHERE task_id = ? AND sequence_number > ?
            ORDER BY sequence_number ASC;
            """,
            (task_id, after_sequence),
        )
        rows = cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_events_for_conversation(self, conversation_id: str) -> list[DomainEvent]:
        """Fetch all events associated with a conversation."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT event_id, task_id, conversation_id, event_type,
                   timestamp_utc, sequence_number, payload_json,
                   causation_event_id, correlation_id
            FROM orchestration_events
            WHERE conversation_id = ?
            ORDER BY sequence_number ASC;
            """,
            (conversation_id,),
        )
        rows = cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    def get_latest_sequence(self, task_id: str) -> int:
        """Get the highest sequence number recorded for a task, or 0 if none."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT MAX(sequence_number) FROM orchestration_events WHERE task_id = ?;",
            (task_id,),
        )
        val = cursor.fetchone()[0]
        return int(val) if val is not None else 0

    def _row_to_event(self, row: Any) -> DomainEvent:
        return DomainEvent(
            event_id=row["event_id"],
            task_id=row["task_id"],
            conversation_id=row["conversation_id"],
            event_type=EventType(row["event_type"]),
            timestamp_utc=row["timestamp_utc"],
            sequence_number=row["sequence_number"],
            payload=json.loads(row["payload_json"]),
            causation_event_id=row["causation_event_id"],
            correlation_id=row["correlation_id"] or "",
        )

    def close(self) -> None:
        """Close SQLite database connection."""
        self._conn.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


__all__ = ["EventStore"]
