"""extensions/cua-computer/src/db.py

Database-first audit and state persistence for JARVIS computer use and input leases.
Follows OpenClaw / JARVIS storage rules:
- Pure SQLite persistence (no JSON/JSONL sidecar files)
- Strict privacy: NEVER logs typed text or secret strings, only char count
- Synchronous write transactions with resilient connection cleanup
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
from pathlib import Path
import sqlite3
import time
from typing import Generator, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH: Path = Path.home() / ".jarvis" / "state" / "jarvis.sqlite"

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS input_leases (
    lease_id TEXT PRIMARY KEY,
    session_id TEXT,
    state TEXT NOT NULL,
    requested_at REAL NOT NULL,
    acquired_at REAL,
    released_at REAL,
    abort_reason TEXT,
    actions_count INTEGER DEFAULT 0,
    duration_ms REAL
);

CREATE TABLE IF NOT EXISTS computer_actions (
    action_id TEXT PRIMARY KEY,
    lease_id TEXT,
    tier INTEGER NOT NULL,
    action_name TEXT NOT NULL,
    target_desc TEXT,
    target_x INTEGER,
    target_y INTEGER,
    chars_typed_count INTEGER DEFAULT 0,
    started_at REAL NOT NULL,
    duration_ms REAL,
    success INTEGER NOT NULL,
    error_code TEXT,
    FOREIGN KEY(lease_id) REFERENCES input_leases(lease_id)
);

CREATE INDEX IF NOT EXISTS idx_leases_time ON input_leases(requested_at);
CREATE INDEX IF NOT EXISTS idx_actions_lease ON computer_actions(lease_id);
"""


class ComputerAuditStore:
    """Manages SQLite audit records for all input leases and executed computer actions."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        else:
            self.db_path = Path(db_path)

        self._ensure_schema()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        try:
            with self._connection() as conn:
                conn.executescript(SCHEMA_DDL)
        except Exception as e:
            logger.error("Failed to initialize computer audit schema: %s", e)

    def record_lease_start(self, lease_id: str, session_id: str, state: str) -> None:
        try:
            now = time.time()
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO input_leases (lease_id, session_id, state, requested_at, acquired_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(lease_id) DO UPDATE SET
                        state=excluded.state,
                        acquired_at=excluded.acquired_at;
                    """,
                    (lease_id, session_id, state, now, now),
                )
        except Exception as e:
            logger.debug("Failed recording lease start: %s", e)

    def record_lease_end(
        self,
        lease_id: str,
        state: str,
        abort_reason: str | None = None,
        actions_count: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        try:
            now = time.time()
            with self._connection() as conn:
                conn.execute(
                    """
                    UPDATE input_leases
                    SET state = ?,
                        released_at = ?,
                        abort_reason = ?,
                        actions_count = ?,
                        duration_ms = ?
                    WHERE lease_id = ?;
                    """,
                    (state, now, abort_reason, actions_count, duration_ms, lease_id),
                )
        except Exception as e:
            logger.debug("Failed recording lease end: %s", e)

    def record_action(
        self,
        action_id: str,
        lease_id: str | None,
        tier: int,
        action_name: str,
        target_desc: str | None,
        target_x: int | None,
        target_y: int | None,
        chars_typed_count: int,
        started_at: float,
        duration_ms: float,
        success: bool,
        error_code: str | None = None,
    ) -> None:
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO computer_actions (
                        action_id, lease_id, tier, action_name,
                        target_desc, target_x, target_y, chars_typed_count,
                        started_at, duration_ms, success, error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        action_id,
                        lease_id,
                        tier,
                        action_name,
                        target_desc,
                        target_x,
                        target_y,
                        chars_typed_count,
                        started_at,
                        duration_ms,
                        1 if success else 0,
                        error_code,
                    ),
                )
        except Exception as e:
            logger.debug("Failed recording action: %s", e)


__all__ = ["ComputerAuditStore", "DEFAULT_DB_PATH"]
