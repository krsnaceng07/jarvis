"""src.agents.self_healing.audit_ledger — SQLite-backed recovery audit log.

OpenClaw parity: persistent, database-first audit recording with zero schema
version bump (pure additive table created with IF NOT EXISTS on first use).
"""

from __future__ import annotations

import collections
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .failure_event import FailureEvent


def _resolve_default_db_path() -> Path:
    """Locate the shared state database path (~/.jarvis/state/jarvis.sqlite)."""
    state_dir = os.environ.get("JARVIS_STATE_DIR")
    if state_dir:
        base = Path(state_dir)
    else:
        base = Path.home() / ".jarvis" / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "jarvis.sqlite"


class RecoveryAuditLedger:
    """Stores self-healing and recovery attempts in SQLite with in-memory fallback."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _resolve_default_db_path()
        self._lock = threading.Lock()
        self._table_initialized = False
        # In-memory circular buffer fallback (retains last 200 events)
        self._memory_buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)

    def _ensure_table(self, conn: sqlite3.Connection) -> None:
        """Create recovery_audit_log table if it doesn't already exist (pure additive)."""
        if self._table_initialized:
            return
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recovery_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                session_key TEXT NOT NULL,
                event_id TEXT NOT NULL,
                category TEXT NOT NULL,
                signature TEXT NOT NULL,
                action TEXT NOT NULL,
                verified INTEGER NOT NULL,
                error_message TEXT,
                details_json TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_recovery_sig ON recovery_audit_log(signature)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recovery_sess ON recovery_audit_log(session_key)"
        )
        conn.commit()
        self._table_initialized = True

    def record_recovery_event(
        self,
        event: FailureEvent,
        action: str,
        verified: bool,
        details: dict[str, Any] | None = None,
        session_key: str = "desktop:hud",
    ) -> None:
        """Record a self-healing recovery attempt and its outcome."""
        record = {
            "timestamp": time.time(),
            "session_key": session_key,
            "event_id": event.event_id,
            "category": event.category.value,
            "signature": event.signature,
            "action": action,
            "verified": 1 if verified else 0,
            "error_message": event.error_message[:500],
            "details_json": json.dumps(details or {}),
        }

        # Always append to in-memory buffer first
        with self._lock:
            self._memory_buffer.append(record)

        # Attempt synchronous SQLite write
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            try:
                self._ensure_table(conn)
                conn.execute(
                    """
                    INSERT INTO recovery_audit_log
                    (timestamp, session_key, event_id, category, signature, action, verified, error_message, details_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["timestamp"],
                        record["session_key"],
                        record["event_id"],
                        record["category"],
                        record["signature"],
                        record["action"],
                        record["verified"],
                        record["error_message"],
                        record["details_json"],
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception as err:
            # Fallback keeps operating in-memory if disk SQLite is locked or unavailable
            print(f"[JARVIS] ⚠️ RecoveryAuditLedger SQLite write failed ({err}); saved to memory")

    def get_recent_recoveries(
        self,
        limit: int = 50,
        session_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve recent recovery records from SQLite or memory buffer."""
        try:
            if self.db_path.exists():
                conn = sqlite3.connect(str(self.db_path), timeout=5.0)
                try:
                    self._ensure_table(conn)
                    conn.row_factory = sqlite3.Row
                    if session_key:
                        cursor = conn.execute(
                            """
                            SELECT * FROM recovery_audit_log
                            WHERE session_key = ?
                            ORDER BY timestamp DESC LIMIT ?
                            """,
                            (session_key, limit),
                        )
                    else:
                        cursor = conn.execute(
                            """
                            SELECT * FROM recovery_audit_log
                            ORDER BY timestamp DESC LIMIT ?
                            """,
                            (limit,),
                        )
                    rows = cursor.fetchall()
                    return [dict(r) for r in rows]
                finally:
                    conn.close()
        except Exception:
            pass

        # Fallback to in-memory buffer
        with self._lock:
            items = list(self._memory_buffer)
            if session_key:
                items = [it for it in items if it["session_key"] == session_key]
            return sorted(items, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_recovery_stats(self) -> dict[str, Any]:
        """Aggregate statistics on total recoveries and verification success rate."""
        records = self.get_recent_recoveries(limit=200)
        total = len(records)
        if total == 0:
            return {"total": 0, "verified_count": 0, "success_rate": 0.0}

        verified_count = sum(1 for r in records if r.get("verified") == 1)
        return {
            "total": total,
            "verified_count": verified_count,
            "success_rate": round(verified_count / total, 3),
        }


__all__ = [
    "RecoveryAuditLedger",
]
