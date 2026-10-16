"""State snapshotting engine for fast replay and checkpointing."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from jarvis_agent.orchestration.state.reducer import RuntimeState


class SnapshotEngine:
    """Manages persistent snapshots of reduced RuntimeState for checkpointing."""

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
        cursor = self._conn.cursor()
        if self._db_path != ":memory:":
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orchestration_snapshots (
                task_id TEXT PRIMARY KEY,
                applied_sequence INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
        """)
        self._conn.commit()

    def save_snapshot(self, state: RuntimeState) -> None:
        """Persist a RuntimeState snapshot for its associated task."""
        if not state.task:
            return
        cursor = self._conn.cursor()
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cursor.execute(
            """
            INSERT INTO orchestration_snapshots (task_id, applied_sequence, state_json, created_at_utc)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                applied_sequence=excluded.applied_sequence,
                state_json=excluded.state_json,
                created_at_utc=excluded.created_at_utc;
            """,
            (
                state.task.task_id,
                state.applied_sequence,
                json.dumps(state.to_dict(), sort_keys=True, separators=(",", ":")),
                now_utc,
            ),
        )
        self._conn.commit()

    def load_snapshot(self, task_id: str) -> RuntimeState | None:
        """Load latest snapshot for a task, returning None if no snapshot exists."""
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT state_json FROM orchestration_snapshots WHERE task_id = ?;",
            (task_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        data = json.loads(row["state_json"])
        return RuntimeState.from_dict(data)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SnapshotEngine:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


__all__ = ["SnapshotEngine"]
