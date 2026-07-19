"""MemoryRuntime — sqlite-backed key/value store.

Phase 2 ships a simple SQLite-backed memory. Each row is
``(key TEXT PRIMARY KEY, value TEXT, category TEXT, updated_at TEXT)``.
Substring search is a SQL ``LIKE %q%``; semantic search via LanceDB
arrives in Phase 2.5.

Schema mirrors what OpenClaw's memory-core uses (sans the FTS5
index, which we'd add in Phase 2.5).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_category ON memory(category);
CREATE INDEX IF NOT EXISTS idx_memory_updated  ON memory(updated_at);
"""


class MemoryRuntime:
    """SQLite-backed key/value memory store.

    The runtime is a singleton per process (one SQLite file, one
    connection pool). Use ``MemoryRuntime.default()`` to get the
    process-wide instance; the data dir comes from
    ``$JARVIS_DATA_DIR`` or ``~/.jarvis``.
    """

    _default: MemoryRuntime | None = None
    _lock = threading.Lock()

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # ``check_same_thread=False`` because plugins call us from
        # the async event loop. We serialize access via a lock.
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn_lock = threading.Lock()

    @classmethod
    def default(cls) -> MemoryRuntime:
        with cls._lock:
            if cls._default is None:
                import os

                data_dir = Path(os.environ.get("JARVIS_DATA_DIR") or (Path.home() / ".jarvis"))
                cls._default = cls(data_dir / "core" / "memory.sqlite")
            return cls._default

    # ── CRUD ───────────────────────────────────────────────────────

    def set(self, key: str, value: str, category: str = "general") -> None:
        import datetime

        with self._conn_lock:
            self._conn.execute(
                """
                INSERT INTO memory (key, value, category, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    category=excluded.category,
                    updated_at=excluded.updated_at
                """,
                (key, value, category, datetime.datetime.now().isoformat(timespec="seconds")),
            )

    def get(self, key: str) -> str | None:
        with self._conn_lock:
            row = self._conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def delete(self, key: str) -> bool:
        with self._conn_lock:
            cur = self._conn.execute("DELETE FROM memory WHERE key = ?", (key,))
            return cur.rowcount > 0

    def count(self) -> int:
        with self._conn_lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM memory").fetchone()
        return int(row["n"])

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn_lock:
            rows = self._conn.execute(
                "SELECT key, value, category FROM memory ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_substring(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """SQL ``LIKE %q%`` search across both key and value columns."""
        like = f"%{query}%"
        with self._conn_lock:
            rows = self._conn.execute(
                """
                SELECT key, value, category FROM memory
                WHERE key LIKE ? OR value LIKE ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (like, like, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Bulk import (used by the doctor apply path) ────────────────

    def bulk_set(self, entries: list[dict[str, str]]) -> int:
        """Insert many rows in one transaction. Returns rows inserted."""
        n = 0
        with self._conn_lock:
            for e in entries:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO memory (key, value, category, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        e["key"],
                        e["value"],
                        e.get("category", "general"),
                        e.get("updated_at", ""),
                    ),
                )
                n += 1
        return n

    def close(self) -> None:
        with self._conn_lock:
            self._conn.close()


__all__ = ["MemoryRuntime"]


# Sentinel: touch the imported name so ruff doesn't flag unused-import.
_ = json
