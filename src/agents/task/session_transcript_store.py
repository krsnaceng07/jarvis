"""jarvis.agents.task.session_transcript_store — SQLite-backed session transcript store.

Stores continuous conversation turns, tool calls, and verified execution records
in SQLite for auditability, session recovery, and multi-step task continuity.

Parity with OpenClaw session transcript storage architecture.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional


def _resolve_default_db_path() -> str:
    """Resolve default SQLite path for session transcripts."""
    try:
        from jarvis_state_core.paths import resolve_agent_sqlite_path

        return resolve_agent_sqlite_path("main")
    except Exception:
        state_dir = os.environ.get("JARVIS_STATE_DIR") or os.path.join(
            os.path.expanduser("~"), ".jarvis", "state"
        )
        return os.path.join(state_dir, "agents", "main", "agent.sqlite")


class SessionTranscriptStore:
    """SQLite-backed transcript store for session turns and verified executions."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        self.db_path = str(db_path) if db_path is not None else _resolve_default_db_path()
        self._lock = threading.Lock()
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        return conn

    def _ensure_schema(self) -> None:
        """Additive schema ensure for session transcripts table."""
        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS session_transcripts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id TEXT NOT NULL,
                            sequence INTEGER NOT NULL,
                            entry_type TEXT NOT NULL,
                            data_json TEXT NOT NULL,
                            verified INTEGER NOT NULL DEFAULT 0,
                            created_at REAL NOT NULL,
                            UNIQUE(session_id, sequence)
                        );
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_session_transcripts_sid_seq
                        ON session_transcripts(session_id, sequence);
                        """
                    )
                    conn.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_session_transcripts_sid_type
                        ON session_transcripts(session_id, entry_type);
                        """
                    )
            finally:
                conn.close()

    def append_entry(
        self,
        session_id: str,
        entry_type: str,
        data: dict[str, Any],
        verified: bool = False,
        timestamp: Optional[float] = None,
    ) -> int:
        """Append a transcript entry with auto-incrementing sequence per session.

        Returns the assigned sequence number.
        """
        ts = timestamp if timestamp is not None else time.time()
        json_str = json.dumps(data, ensure_ascii=False)
        verif_int = 1 if verified else 0

        with self._lock:
            conn = self._get_connection()
            try:
                with conn:
                    cursor = conn.execute(
                        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM session_transcripts WHERE session_id = ?",
                        (session_id,),
                    )
                    next_seq = cursor.fetchone()[0]
                    conn.execute(
                        """
                        INSERT INTO session_transcripts
                        (session_id, sequence, entry_type, data_json, verified, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (session_id, next_seq, entry_type, json_str, verif_int, ts),
                    )
                    return int(next_seq)
            finally:
                conn.close()

    def get_recent_entries(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent entries for a session ordered by sequence ascending."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    SELECT sequence, entry_type, data_json, verified, created_at
                    FROM session_transcripts
                    WHERE session_id = ?
                    ORDER BY sequence DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                )
                rows = cursor.fetchall()
                results = []
                for row in reversed(rows):
                    results.append(
                        {
                            "sequence": row["sequence"],
                            "entry_type": row["entry_type"],
                            "data": json.loads(row["data_json"]),
                            "verified": bool(row["verified"]),
                            "created_at": row["created_at"],
                        }
                    )
                return results
            finally:
                conn.close()

    def get_last_execution_record(self, session_id: str) -> Optional[dict[str, Any]]:
        """Retrieve the latest execution record for a session."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    SELECT sequence, entry_type, data_json, verified, created_at
                    FROM session_transcripts
                    WHERE session_id = ? AND entry_type = 'execution_record'
                    ORDER BY sequence DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "sequence": row["sequence"],
                        "entry_type": row["entry_type"],
                        "data": json.loads(row["data_json"]),
                        "verified": bool(row["verified"]),
                        "created_at": row["created_at"],
                    }
                return None
            finally:
                conn.close()


__all__ = ["SessionTranscriptStore"]
