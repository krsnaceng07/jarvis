"""Per-agent SQLite database helper.

Mirrors OpenClaw's ``src/state/openclaw-agent-db.ts`` (the
filesystem + permissions + cache layer; the heavy schema
ensurer is a follow-up commit). The Python port focuses
on:

- ``open_agent_database(options)`` — open a per-agent
  SQLite DB, applying the canonical pragmas and ensuring
  the parent dir + file are private by contract
- ``close_agent_database(pathname)`` / ``close_all_agent_databases``
  — handle-cache management for tests + doctor
- ``resolve_agent_sqlite_path(agent_id, env)`` — re-export
  of the path helper from ``paths.py``
- ``is_agent_database_open()`` — diagnostic for tests
- ``inspect_agent_database_owner(pathname)`` — read a
  database's owner / status without mutating it

The full agent schema + session migrations are a
follow-up commit (Phase 5.17c). The Python port keeps
the same public surface as the TS port and uses
``ensure_agent_database_permissions`` to apply the
canonical mode bits.
"""

from __future__ import annotations

import os
import json
import sqlite3
import threading
from dataclasses import dataclass
from typing import Callable, Literal, Optional, TypedDict

from .contract import SQLITE_BUSY_TIMEOUT_MS
from .paths import resolve_agent_sqlite_path
from .permissions import ensure_agent_database_permissions


AgentDatabaseOwnerStatus = Literal["owned", "unowned", "unreadable"]


@dataclass
class AgentDatabaseHandle:
    """Open per-agent SQLite database handle + lifecycle.

    Mirrors OpenClaw's ``OpenClawAgentDatabase``.
    """

    agent_id: str
    db: sqlite3.Connection
    path: str


class AgentDatabaseOptions(TypedDict, total=False):
    agent_id: str
    env: Optional[dict[str, str]]
    path: Optional[str]
    connection_factory: Optional[Callable[[], sqlite3.Connection]]


def ensure_agent_session_schema(db: sqlite3.Connection) -> None:
    """Ensure additive per-agent session tables exist."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            session_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            cwd TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agent_session_entries (
            session_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            entry_id TEXT NOT NULL,
            entry_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (session_id, sequence),
            UNIQUE (session_id, entry_id),
            FOREIGN KEY (session_id) REFERENCES agent_sessions(session_id)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_agent_session_entries_id
            ON agent_session_entries(session_id, entry_id);
        """
    )


def ensure_agent_session(
    handle: AgentDatabaseHandle, session_id: str, cwd: str, timestamp: str
) -> None:
    ensure_agent_session_schema(handle.db)
    handle.db.execute(
        """INSERT OR IGNORE INTO agent_sessions
           (session_id, agent_id, cwd, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, handle.agent_id, cwd, timestamp, timestamp),
    )


def append_agent_session_entry(
    handle: AgentDatabaseHandle,
    session_id: str,
    entry: dict,
    timestamp: str,
) -> None:
    ensure_agent_session_schema(handle.db)
    with handle.db:
        row = handle.db.execute(
            "SELECT COALESCE(MAX(sequence), -1) + 1 FROM agent_session_entries WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        sequence = int(row[0])
        handle.db.execute(
            """INSERT INTO agent_session_entries
               (session_id, sequence, entry_id, entry_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, sequence, str(entry["id"]), json.dumps(entry), timestamp),
        )
        handle.db.execute(
            "UPDATE agent_sessions SET updated_at = ? WHERE session_id = ?",
            (timestamp, session_id),
        )


def load_agent_session_entries(handle: AgentDatabaseHandle, session_id: str) -> list[dict]:
    ensure_agent_session_schema(handle.db)
    rows = handle.db.execute(
        "SELECT entry_json FROM agent_session_entries WHERE session_id = ? ORDER BY sequence",
        (session_id,),
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


class _AgentDatabaseOwnerInspection:
    """Mirrors OpenClaw's ``OpenClawAgentDatabaseOwnerInspection``."""

    def __init__(
        self,
        status: AgentDatabaseOwnerStatus,
        agent_id: Optional[str] = None,
    ) -> None:
        self.status = status
        self.agent_id = agent_id


# ── Cache + lifecycle ─────────────────────────────────────


_cache_lock = threading.Lock()
_cached_databases: dict[str, AgentDatabaseHandle] = {}


def _open_sqlite(pathname: str) -> sqlite3.Connection:
    """Open a per-agent SQLite connection with canonical pragmas."""
    conn = sqlite3.connect(pathname)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_MS)}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def open_agent_database(options: dict) -> AgentDatabaseHandle:
    """Open or return a cached per-agent database.

    Mirrors ``openOpenClawAgentDatabase``. The Python port
    applies permission hardening + the standard pragmas
    and caches the handle by absolute path.
    """
    if not isinstance(options, dict):
        raise TypeError("open_agent_database: options must be a dict")
    agent_id = options.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("open_agent_database: agent_id is required")
    env = options.get("env")
    custom_path = options.get("path")
    custom_factory = options.get("connection_factory")
    pathname = os.path.abspath(custom_path or resolve_agent_sqlite_path(agent_id, env))
    with _cache_lock:
        cached = _cached_databases.get(pathname)
        if cached is not None:
            if cached.agent_id != agent_id:
                raise RuntimeError(
                    f"Agent database {pathname} is already open for agent "
                    f"{cached.agent_id}; requested agent {agent_id}."
                )
            return cached
        # Open under the cache lock so concurrent
        # ``open_agent_database`` callers do not race the
        # underlying ``sqlite3.connect`` (which can refuse
        # with "database is locked" when two processes
        # open the same file simultaneously).
        ensure_agent_database_permissions(agent_id, pathname, env)
        if custom_factory is not None:
            db = custom_factory()
        else:
            db = _open_sqlite(pathname)
        ensure_agent_session_schema(db)
        handle = AgentDatabaseHandle(agent_id=agent_id, db=db, path=pathname)
        _cached_databases[pathname] = handle
        return handle


def close_agent_database(pathname: str) -> None:
    """Close one cached per-agent database handle."""
    resolved = os.path.abspath(pathname)
    with _cache_lock:
        cached = _cached_databases.pop(resolved, None)
    if cached is not None:
        try:
            cached.db.close()
        except Exception:  # noqa: BLE001
            pass


def close_all_agent_databases() -> None:
    """Close every cached per-agent database handle."""
    with _cache_lock:
        handles = list(_cached_databases.values())
        _cached_databases.clear()
    for cached in handles:
        try:
            cached.db.close()
        except Exception:  # noqa: BLE001
            pass


def is_agent_database_open(pathname: Optional[str] = None) -> bool:
    """Return True when any (or one) cached per-agent DB is still open."""
    with _cache_lock:
        if pathname is None:
            return len(_cached_databases) > 0
        return os.path.abspath(pathname) in _cached_databases


# ── Inspection ────────────────────────────────────────────


def inspect_agent_database_owner(pathname: str) -> _AgentDatabaseOwnerInspection:
    """Read a database's owner / status without mutating it.

    Mirrors ``inspectOpenClawAgentDatabaseOwner``. The
    Python port probes the file: missing files report
    ``unowned``; unreachable / non-SQLite files report
    ``unreadable``; reachable files report ``owned``
    (the Python port's agent DB does not yet own a
    ``schema_meta`` table, so the owner check is a
    reachability probe; future work adds schema shape
    recognition).
    """
    resolved = os.path.abspath(pathname)
    if not os.path.exists(resolved):
        return _AgentDatabaseOwnerInspection(status="unowned")
    conn = None
    try:
        try:
            conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
        except Exception:  # noqa: BLE001
            return _AgentDatabaseOwnerInspection(status="unreadable")
        # Probe: SQLite refuses to open a non-database file
        # as a database (e.g. "file is not a database").
        # ``PRAGMA schema_version`` is the cheapest read
        # that still requires the header to be valid.
        try:
            conn.execute("PRAGMA schema_version").fetchone()
        except sqlite3.DatabaseError:
            return _AgentDatabaseOwnerInspection(status="unreadable")
        return _AgentDatabaseOwnerInspection(status="owned")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def reset_agent_database_state_for_tests() -> None:
    """Clear the per-process cache for test isolation."""
    close_all_agent_databases()


__all__ = [
    "AgentDatabaseHandle",
    "AgentDatabaseOptions",
    "AgentDatabaseOwnerStatus",
    "append_agent_session_entry",
    "close_agent_database",
    "close_all_agent_databases",
    "inspect_agent_database_owner",
    "is_agent_database_open",
    "ensure_agent_session",
    "ensure_agent_session_schema",
    "load_agent_session_entries",
    "open_agent_database",
    "reset_agent_database_state_for_tests",
    "resolve_agent_sqlite_path",
]
