"""Durable Gateway-owned state for Codex conversation controls.

The command layer remains transport-agnostic: hosts may pass these methods as
``CodexCommandContext`` callbacks. The table is additive and created lazily so
older JARVIS state databases remain readable.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS codex_conversation_state (
    session_id TEXT PRIMARY KEY,
    thread_id TEXT,
    cwd TEXT,
    model TEXT,
    provider TEXT,
    fast INTEGER,
    permissions TEXT,
    updated_at INTEGER NOT NULL
)
""".strip()


class CodexConversationStore:
    """Persist Codex binding and per-conversation preferences in SQLite."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            from jarvis_state_core import resolve_state_sqlite_path

            db_path = resolve_state_sqlite_path()
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(_CREATE_TABLE)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA busy_timeout=3000")
        return connection

    def read_binding(self, session_id: str) -> dict[str, Any] | None:
        row = self._read_row(session_id)
        if row is None or row[0] is None:
            return None
        result: dict[str, Any] = {"threadId": row[0]}
        for column, key in ((row[1], "cwd"), (row[2], "model"), (row[3], "provider")):
            if column is not None:
                result[key] = column
        return result

    def update_binding(self, session_id: str, value: dict[str, Any] | None) -> None:
        current = self._read_row(session_id)
        values = {
            "thread_id": value.get("threadId") if value else None,
            "cwd": value.get("cwd") if value else None,
            "model": value.get("model") if value else None,
            "provider": value.get("provider") if value else None,
            "fast": current[4] if current else None,
            "permissions": current[5] if current else None,
        }
        self._write(session_id, values)

    def read_state(self, session_id: str) -> dict[str, Any]:
        row = self._read_row(session_id)
        if row is None:
            return {}
        state: dict[str, Any] = {}
        if row[4] is not None:
            state["fast"] = bool(row[4])
        if row[5] is not None:
            state["permissions"] = row[5]
        return state

    def update_state(self, session_id: str, values: dict[str, Any]) -> None:
        current = self._read_row(session_id)
        merged = {
            "thread_id": current[0] if current else None,
            "cwd": current[1] if current else None,
            "model": values.get("model", current[2] if current else None),
            "provider": current[3] if current else None,
            "fast": values.get("fast", current[4] if current else None),
            "permissions": values.get("permissions", current[5] if current else None),
        }
        self._write(session_id, merged)

    def callbacks(self, session_id: str) -> dict[str, Any]:
        """Return callback values accepted by ``CodexCommandContext``."""
        return {
            "binding_update_fn": lambda value: self.update_binding(session_id, value),
            "state_read_fn": lambda: self.read_state(session_id),
            "state_update_fn": lambda values: self.update_state(session_id, values),
        }

    def _read_row(self, session_id: str) -> tuple[Any, ...] | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT thread_id, cwd, model, provider, fast, permissions "
                "FROM codex_conversation_state WHERE session_id = ?",
                (session_id,),
            ).fetchone()

    def _write(self, session_id: str, values: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO codex_conversation_state
                    (session_id, thread_id, cwd, model, provider, fast, permissions, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    cwd = excluded.cwd,
                    model = excluded.model,
                    provider = excluded.provider,
                    fast = excluded.fast,
                    permissions = excluded.permissions,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    values["thread_id"],
                    values["cwd"],
                    values["model"],
                    values["provider"],
                    None if values["fast"] is None else int(values["fast"]),
                    values["permissions"],
                    int(time.time() * 1000),
                ),
            )


__all__ = ["CodexConversationStore"]
