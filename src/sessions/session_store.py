"""jarvis.sessions.session_store — SessionStore protocol + impls.

OpenClaw parity: mirrors the shape of the OpenClaw session
store (the TS side uses a SQLite-backed store; the Python
port ships an in-memory implementation in this slice).

The store is the per-agent, per-session-key record
authoritative. It owns:
- The session metadata (kind, owner agent, created/updated).
- A list of (id, kind, payload) transcript entries.
- Optional ``parent_session_key`` and ``thread_id`` for
  channel/thread sub-sessions.

The store is single-process; the Phase 5.14b SQLite-backed
port is gated on user schema approval (AGENTS.md §"SQLite
schema gate") and will reuse the same protocol.

Phase 5.20 — second consumer of ``jarvis_state_core``:
the ``SqliteSessionStore`` class implements the same
``SessionStore`` protocol but uses
``jarvis_state_core.StateDatabase`` for connection
management. The standard pragmas (busy_timeout, WAL,
foreign_keys) apply transparently; the per-store-path
FIFO queue is shared with the rest of the runtime so
concurrent writes serialize correctly.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One session's metadata + transcript entries.

    The Python port is structurally identical to the OpenClaw
    session-state event kinds: every entry is a
    ``(id, kind, payload)`` triple; the metadata captures
    agent / kind / created / updated at.
    """

    session_key: str
    agent_id: str
    kind: str  # "direct" | "channel" | "thread" | "cron" | "unknown"
    created_at: str
    updated_at: str
    parent_session_key: str | None = None
    thread_id: str | None = None
    entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def with_entry(self, entry: dict[str, Any]) -> "SessionRecord":
        """Return a new ``SessionRecord`` with ``entry`` appended.

        Mirrors the immutable-update pattern used in the
        OpenClaw store: every write produces a new record;
        readers see the snapshot they grabbed.
        """
        now = _now_iso()
        return SessionRecord(
            session_key=self.session_key,
            agent_id=self.agent_id,
            kind=self.kind,
            created_at=self.created_at,
            updated_at=now,
            parent_session_key=self.parent_session_key,
            thread_id=self.thread_id,
            entries=(*self.entries, entry),
        )


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _new_session_id() -> str:
    """Return a fresh UUID-shaped session id."""
    return str(uuid.uuid4())


class SessionStore(Protocol):
    """The protocol the agent_runtime and runner code use.

    Implementations are responsible for atomicity (the
    Python in-memory variant uses a ``threading.Lock`` per
    session; the SQLite-backed variant will use a
    transaction).
    """

    def get_or_create(
        self,
        *,
        session_key: str,
        agent_id: str,
        kind: str,
        parent_session_key: str | None = None,
        thread_id: str | None = None,
    ) -> SessionRecord: ...

    def append_entry(
        self, session_key: str, entry: dict[str, Any]
    ) -> SessionRecord: ...

    def get(self, session_key: str) -> SessionRecord | None: ...

    def list_sessions(self, agent_id: str | None = None) -> list[SessionRecord]:
        """Return every session, optionally filtered by ``agent_id``."""
        ...


class InMemorySessionStore:
    """Thread-safe in-memory implementation of the ``SessionStore`` protocol.

    Single-process; sessions live for the process lifetime. The
    ``reset`` helper is the test surface for clearing the
    store between tests.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Drop every session. Test-only helper."""
        with self._lock:
            self._sessions.clear()

    def get(self, session_key: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_key)

    def get_or_create(
        self,
        *,
        session_key: str,
        agent_id: str,
        kind: str,
        parent_session_key: str | None = None,
        thread_id: str | None = None,
    ) -> SessionRecord:
        with self._lock:
            existing = self._sessions.get(session_key)
            if existing is not None:
                return existing
            now = _now_iso()
            record = SessionRecord(
                session_key=session_key,
                agent_id=agent_id,
                kind=kind,
                created_at=now,
                updated_at=now,
                parent_session_key=parent_session_key,
                thread_id=thread_id,
            )
            self._sessions[session_key] = record
            return record

    def append_entry(
        self, session_key: str, entry: dict[str, Any]
    ) -> SessionRecord:
        with self._lock:
            current = self._sessions.get(session_key)
            if current is None:
                raise KeyError(
                    f"session_key {session_key!r} not found; call get_or_create first"
                )
            updated = current.with_entry(entry)
            self._sessions[session_key] = updated
            return updated

    def list_sessions(self, agent_id: str | None = None) -> list[SessionRecord]:
        with self._lock:
            sessions = list(self._sessions.values())
        if agent_id is not None:
            sessions = [s for s in sessions if s.agent_id == agent_id]
        return sessions


# Module-level singleton for the host runtime; tests construct
# their own per-test stores via ``InMemorySessionStore()``.
_default_store: InMemorySessionStore | None = None
_default_store_lock = threading.Lock()


def get_default_session_store() -> InMemorySessionStore:
    """Return the process-wide default ``InMemorySessionStore``.

    Lazy-initialized on first call so importing this module
    doesn't open any state. Tests should construct their own
    ``InMemorySessionStore()`` to avoid sharing state.
    """
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = InMemorySessionStore()
        return _default_store


def reset_default_session_store() -> None:
    """Reset the process-wide default store. Test-only helper."""
    global _default_store
    with _default_store_lock:
        if _default_store is not None:
            _default_store.reset()


# ── Phase 5.20: SQLite-backed store via jarvis_state_core ─────


# Schema for the SQLite-backed ``sessions`` table. The
# schema follows the same fields the ``SessionRecord``
# dataclass carries + a JSON-encoded ``entries`` column
# for the transcript. The ``state_db.ensure_schema`` call
# in the constructor can extend this with the additive
# state-DB baseline.
SQLITE_SESSIONS_SCHEMA_SQL: str = (
    "CREATE TABLE IF NOT EXISTS sessions ("
    "session_key TEXT PRIMARY KEY, "
    "agent_id TEXT NOT NULL, "
    "kind TEXT NOT NULL, "
    "created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, "
    "parent_session_key TEXT, "
    "thread_id TEXT, "
    "entries_json TEXT NOT NULL DEFAULT '[]'"
    ");"
    "CREATE INDEX IF NOT EXISTS idx_sessions_agent "
    "ON sessions(agent_id);"
)


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Mirrors the ``_now_iso`` helper used by the
    in-memory variant.
    """
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _new_session_id() -> str:
    """Return a fresh UUID-shaped session id."""
    return str(uuid.uuid4())


class SqliteSessionStore:
    """SQLite-backed ``SessionStore`` implementation.

    Phase 5.20 — second consumer of ``jarvis_state_core``:
    the standard pragmas (busy_timeout=5s, WAL,
    foreign_keys=ON) apply transparently via
    ``StateDatabase.open()``, and the per-store-path
    FIFO queue is shared with the rest of the runtime.

    The store mirrors the ``SessionStore`` protocol
    surface (``get_or_create`` / ``append_entry`` /
    ``get`` / ``list_sessions``) so callers that
    accept the protocol can swap implementations
    without code changes.

    Concurrency:
    - Same-process writes serialize through the
      ``jarvis_state_core`` per-store-path queue
      (``run_write_transaction``); the
      ``StateDatabase`` is built once and cached
    - The ``InMemorySessionStore`` uses a
      ``threading.Lock`` for the same guarantee; the
      SQLite variant uses BEGIN IMMEDIATE for
      cross-process correctness
    """

    def __init__(
        self,
        options: Optional["jarvis_state_core.StateDatabaseOptions"] = None,
        *,
        connection_factory: Optional[Callable[[], sqlite3.Connection]] = None,
        env: Optional[dict[str, str]] = None,
        path: Optional[str] = None,
    ) -> None:
        """Build the store from a ``StateDatabaseOptions`` bag.

        Mirrors the OpenClaw pattern of accepting a
        connection factory + path overrides. The
        Python port uses ``jarvis_state_core`` so the
        options bag is the same shape as every other
        2nd consumer (sessions, state_core).
        """
        # Local import keeps the module's import cost
        # low for callers that only use the in-memory
        # variant (the default in tests).
        import jarvis_state_core

        if options is None:
            if connection_factory is None:
                raise ValueError(
                    "SqliteSessionStore: connection_factory is required "
                    "(host must wire the canonical state DB)"
                )
            options = jarvis_state_core.StateDatabaseOptions(
                connection_factory=connection_factory,
                env=env,
                path=path,
            )
        self._state_db = jarvis_state_core.StateDatabase(options)
        # Lazy schema bootstrap: the first call opens a
        # connection + ensures the ``sessions`` table
        # exists. The construction itself is cheap.
        self._schema_ensured = False
        self._schema_lock = threading.Lock()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Run the ``sessions`` DDL on a fresh connection.

        Idempotent; the helper is a one-shot per
        instance (the ``_schema_ensured`` flag guards
        against re-running on every open).
        """
        if self._schema_ensured:
            return
        with self._schema_lock:
            if self._schema_ensured:
                return
            conn.executescript(SQLITE_SESSIONS_SCHEMA_SQL)
            conn.commit()
            self._schema_ensured = True

    def _row_to_record(self, row: sqlite3.Row) -> SessionRecord:
        """Map a ``sessions`` row to a ``SessionRecord``.

        Defensive: the ``entries_json`` is parsed with
        a fallback to an empty tuple on malformed
        input (the in-memory variant already filters
        out malformed entries; the SQLite variant
        matches by returning an empty entries list).
        """
        entries_raw = row["entries_json"] or "[]"
        try:
            entries_list = json.loads(entries_raw)
        except (TypeError, ValueError):
            entries_list = []
        if not isinstance(entries_list, list):
            entries_list = []
        return SessionRecord(
            session_key=row["session_key"],
            agent_id=row["agent_id"],
            kind=row["kind"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            parent_session_key=row["parent_session_key"],
            thread_id=row["thread_id"],
            entries=tuple(entries_list),
        )

    def get(self, session_key: str) -> Optional[SessionRecord]:
        """Read one session by key.

        Mirrors ``InMemorySessionStore.get``. Returns
        ``None`` when the row doesn't exist.
        """
        import asyncio

        async def _body() -> Optional[SessionRecord]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT session_key, agent_id, kind, created_at, "
                    "updated_at, parent_session_key, thread_id, "
                    "entries_json FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_record(row)
            finally:
                conn.close()

        return asyncio.run(_body())

    def get_or_create(
        self,
        *,
        session_key: str,
        agent_id: str,
        kind: str,
        parent_session_key: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> SessionRecord:
        """Get the existing session or create a new one.

        Mirrors ``InMemorySessionStore.get_or_create``.
        The create path uses ``INSERT ... ON CONFLICT
        DO NOTHING`` so concurrent callers race-safely
        to the same row.
        """
        import asyncio

        async def _body() -> SessionRecord:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                now = _now_iso()
                # ``INSERT OR IGNORE`` is the SQLite idiom
                # for the ``ON CONFLICT DO NOTHING`` race
                # the in-memory variant handles via the
                # ``threading.Lock``.
                conn.execute(
                    "INSERT OR IGNORE INTO sessions ("
                    "session_key, agent_id, kind, created_at, "
                    "updated_at, parent_session_key, thread_id, "
                    "entries_json"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, '[]')",
                    (
                        session_key,
                        agent_id,
                        kind,
                        now,
                        now,
                        parent_session_key,
                        thread_id,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT session_key, agent_id, kind, created_at, "
                    "updated_at, parent_session_key, thread_id, "
                    "entries_json FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                assert row is not None
                return self._row_to_record(row)
            finally:
                conn.close()

        return asyncio.run(_body())

    def append_entry(
        self, session_key: str, entry: dict[str, Any]
    ) -> SessionRecord:
        """Append ``entry`` to the session's transcript.

        Mirrors ``InMemorySessionStore.append_entry``.
        Uses ``json_set`` semantics by reading the
        current entries list, appending, and writing
        back. A concurrent writer that beats us to the
        row would clobber its entry; the
        ``jarvis_state_core`` per-store-path FIFO
        serializes the writes for the same store
        process.
        """
        import asyncio

        async def _body() -> SessionRecord:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        "SELECT entries_json FROM sessions "
                        "WHERE session_key = ?",
                        (session_key,),
                    ).fetchone()
                    if row is None:
                        raise KeyError(
                            f"session_key {session_key!r} not found; "
                            "call get_or_create first"
                        )
                    try:
                        entries_list = json.loads(row["entries_json"] or "[]")
                    except (TypeError, ValueError):
                        entries_list = []
                    if not isinstance(entries_list, list):
                        entries_list = []
                    entries_list.append(dict(entry))
                    now = _now_iso()
                    conn.execute(
                        "UPDATE sessions SET entries_json = ?, updated_at = ? "
                        "WHERE session_key = ?",
                        (
                            json.dumps(entries_list, separators=(",", ":")),
                            now,
                            session_key,
                        ),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                # Re-read for the return value.
                row = conn.execute(
                    "SELECT session_key, agent_id, kind, created_at, "
                    "updated_at, parent_session_key, thread_id, "
                    "entries_json FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                assert row is not None
                return self._row_to_record(row)
            finally:
                conn.close()

        return asyncio.run(_body())

    def list_sessions(
        self, agent_id: Optional[str] = None
    ) -> list[SessionRecord]:
        """Return every session, optionally filtered by ``agent_id``.

        Mirrors ``InMemorySessionStore.list_sessions``.
        """
        import asyncio

        async def _body() -> list[SessionRecord]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                if agent_id is None:
                    rows = conn.execute(
                        "SELECT session_key, agent_id, kind, created_at, "
                        "updated_at, parent_session_key, thread_id, "
                        "entries_json FROM sessions ORDER BY created_at ASC"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT session_key, agent_id, kind, created_at, "
                        "updated_at, parent_session_key, thread_id, "
                        "entries_json FROM sessions "
                        "WHERE agent_id = ? ORDER BY created_at ASC",
                        (agent_id,),
                    ).fetchall()
                return [self._row_to_record(row) for row in rows]
            finally:
                conn.close()

        return asyncio.run(_body())

    def reset(self) -> None:
        """Drop every session. Test-only helper."""
        import asyncio

        async def _body() -> None:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                conn.execute("DELETE FROM sessions;")
                conn.commit()
            finally:
                conn.close()

        asyncio.run(_body())


__all__ = [
    "InMemorySessionStore",
    "SQLITE_SESSIONS_SCHEMA_SQL",
    "SessionRecord",
    "SessionStore",
    "SqliteSessionStore",
    "get_default_session_store",
    "reset_default_session_store",
]
