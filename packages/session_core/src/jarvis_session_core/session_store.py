"""jarvis_session_core.session_store — SessionStore protocol + impls.

OpenClaw parity: mirrors the shape of the OpenClaw session
store (the TS side uses a SQLite-backed store; the Python
port ships an in-memory implementation and a SQLite-backed implementation).

The store is the per-agent, per-session-key record
authoritative. It owns:
- The session metadata (kind, owner agent, created/updated).
- A list of (id, kind, payload) transcript entries.
- Optional ``parent_session_key`` and ``thread_id`` for
  channel/thread sub-sessions.
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
    session_started_at: str = ""
    last_interaction_at: str = ""
    created_actor: str | None = None
    parent_session_key: str | None = None
    thread_id: str | None = None
    entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    # Route pin: the resolved ``provider/model`` ref + harness runtime id
    # owning this session's turns.
    model_ref: str | None = None
    agent_runtime: str | None = None

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
            session_started_at=self.session_started_at,
            last_interaction_at=now,
            created_actor=self.created_actor,
            parent_session_key=self.parent_session_key,
            thread_id=self.thread_id,
            entries=(*self.entries, entry),
            model_ref=self.model_ref,
            agent_runtime=self.agent_runtime,
        )


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
        created_actor: str | None = None,
    ) -> SessionRecord: ...

    def rollover(self, session_key: str) -> None:
        """Rollover an existing session (archive it so the next get_or_create makes a new one)."""
        ...

    def append_entry(self, session_key: str, entry: dict[str, Any]) -> SessionRecord: ...

    def get(self, session_key: str) -> SessionRecord | None: ...

    def set_route_pin(
        self,
        session_key: str,
        *,
        model_ref: str | None = None,
        agent_runtime: str | None = None,
    ) -> SessionRecord | None:
        """Record (or clear) the session's route pin."""
        ...

    def patch(
        self,
        session_key: str,
        *,
        kind: str | None = None,
        model_ref: str | None = None,
        agent_runtime: str | None = None,
        created_actor: str | None = None,
        parent_session_key: str | None = None,
        thread_id: str | None = None,
    ) -> SessionRecord | None:
        """Update mutable fields of a session record."""
        ...

    def delete(self, session_key: str) -> bool:
        """Delete a session record by key."""
        ...

    def recover(self, session_key: str, agent_id: str = "default") -> SessionRecord:
        """Recover or re-instantiate an uncommitted/lost session record."""
        ...

    def list_sessions(self, agent_id: str | None = None) -> list[SessionRecord]:
        """Return every session, optionally filtered by ``agent_id``."""
        ...

    def search_sessions(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """Search session transcripts for query."""
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

    def set_route_pin(
        self,
        session_key: str,
        *,
        model_ref: str | None = None,
        agent_runtime: str | None = None,
    ) -> SessionRecord | None:
        with self._lock:
            current = self._sessions.get(session_key)
            if current is None:
                return None
            updated = SessionRecord(
                session_key=current.session_key,
                agent_id=current.agent_id,
                kind=current.kind,
                created_at=current.created_at,
                updated_at=current.updated_at,
                session_started_at=current.session_started_at,
                last_interaction_at=current.last_interaction_at,
                created_actor=current.created_actor,
                parent_session_key=current.parent_session_key,
                thread_id=current.thread_id,
                entries=current.entries,
                model_ref=model_ref,
                agent_runtime=agent_runtime,
            )
            self._sessions[session_key] = updated
            return updated

    def rollover(self, session_key: str) -> None:
        with self._lock:
            if session_key in self._sessions:
                old = self._sessions[session_key]
                archived_key = f"{session_key}_archived_{_now_iso().replace(':', '')}"
                new_old = SessionRecord(
                    session_key=archived_key,
                    agent_id=old.agent_id,
                    kind=old.kind,
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                    session_started_at=old.session_started_at,
                    last_interaction_at=old.last_interaction_at,
                    created_actor=old.created_actor,
                    parent_session_key=old.parent_session_key,
                    thread_id=old.thread_id,
                    entries=old.entries,
                    model_ref=old.model_ref,
                    agent_runtime=old.agent_runtime,
                )
                self._sessions[archived_key] = new_old
                del self._sessions[session_key]

    def get_or_create(
        self,
        *,
        session_key: str,
        agent_id: str,
        kind: str,
        parent_session_key: str | None = None,
        thread_id: str | None = None,
        created_actor: str | None = None,
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
                session_started_at=now,
                last_interaction_at=now,
                created_actor=created_actor,
                parent_session_key=parent_session_key,
                thread_id=thread_id,
            )
            self._sessions[session_key] = record
            return record

    def append_entry(self, session_key: str, entry: dict[str, Any]) -> SessionRecord:
        with self._lock:
            current = self._sessions.get(session_key)
            if current is None:
                raise KeyError(f"session_key {session_key!r} not found; call get_or_create first")
            updated = current.with_entry(entry)
            self._sessions[session_key] = updated
            return updated

    def list_sessions(self, agent_id: str | None = None) -> list[SessionRecord]:
        with self._lock:
            sessions = list(self._sessions.values())
        if agent_id is not None:
            sessions = [s for s in sessions if s.agent_id == agent_id]
        return sessions

    def search_sessions(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            results: list[dict[str, Any]] = []
            for s in self._sessions.values():
                for entry in s.entries:
                    if entry.get("kind") in ("user_message", "assistant_message"):
                        payload = entry.get("payload")
                        text = payload.get("text", "") if isinstance(payload, dict) else ""
                        if query.lower() in text.lower():
                            results.append(
                                {
                                    "session_key": s.session_key,
                                    "role": "user"
                                    if entry.get("kind") == "user_message"
                                    else "assistant",
                                    "timestamp": s.updated_at,
                                    "excerpt": text,
                                }
                            )
                            if len(results) >= limit:
                                return results
            return results

    def patch(
        self,
        session_key: str,
        *,
        kind: str | None = None,
        model_ref: str | None = None,
        agent_runtime: str | None = None,
        created_actor: str | None = None,
        parent_session_key: str | None = None,
        thread_id: str | None = None,
    ) -> SessionRecord | None:
        with self._lock:
            existing = self._sessions.get(session_key)
            if existing is None:
                return None
            updated = SessionRecord(
                session_key=existing.session_key,
                agent_id=existing.agent_id,
                kind=kind if kind is not None else existing.kind,
                created_at=existing.created_at,
                updated_at=_now_iso(),
                session_started_at=existing.session_started_at,
                last_interaction_at=existing.last_interaction_at,
                created_actor=created_actor
                if created_actor is not None
                else existing.created_actor,
                parent_session_key=parent_session_key
                if parent_session_key is not None
                else existing.parent_session_key,
                thread_id=thread_id if thread_id is not None else existing.thread_id,
                entries=existing.entries,
                model_ref=model_ref if model_ref is not None else existing.model_ref,
                agent_runtime=agent_runtime
                if agent_runtime is not None
                else existing.agent_runtime,
            )
            self._sessions[session_key] = updated
            return updated

    def delete(self, session_key: str) -> bool:
        with self._lock:
            if session_key in self._sessions:
                del self._sessions[session_key]
                return True
            return False

    def recover(self, session_key: str, agent_id: str = "default") -> SessionRecord:
        with self._lock:
            existing = self._sessions.get(session_key)
            if existing is not None:
                return existing
        return self.get_or_create(session_key=session_key, agent_id=agent_id, kind="direct")


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


# ── SQLite-backed store via jarvis_state_core ─────


SQLITE_SESSIONS_SCHEMA_SQL: str = (
    "CREATE TABLE IF NOT EXISTS sessions ("
    "session_key TEXT PRIMARY KEY, "
    "agent_id TEXT NOT NULL, "
    "kind TEXT NOT NULL, "
    "created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, "
    "parent_session_key TEXT, "
    "thread_id TEXT, "
    "session_started_at TEXT NOT NULL DEFAULT '', "
    "last_interaction_at TEXT NOT NULL DEFAULT '', "
    "created_actor TEXT, "
    "entries_json TEXT NOT NULL DEFAULT '[]', "
    "model_ref TEXT, "
    "agent_runtime TEXT"
    ");"
    "CREATE INDEX IF NOT EXISTS idx_sessions_agent "
    "ON sessions(agent_id);"
)


class SqliteSessionStore:
    """SQLite-backed ``SessionStore`` implementation.

    Uses ``jarvis_state_core`` for connection management.
    """

    def __init__(
        self,
        options: Optional[Any] = None,
        *,
        connection_factory: Optional[Callable[[], sqlite3.Connection]] = None,
        env: Optional[dict[str, str]] = None,
        path: Optional[str] = None,
    ) -> None:
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
        self._schema_ensured = False
        self._schema_lock = threading.Lock()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Run the ``sessions`` DDL on a fresh connection.

        Idempotent; the helper is a one-shot per instance.
        """
        if self._schema_ensured:
            return
        with self._schema_lock:
            if self._schema_ensured:
                return
            conn.executescript(SQLITE_SESSIONS_SCHEMA_SQL)
            conn.executescript(
                "CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5("
                "session_key UNINDEXED, "
                "role UNINDEXED, "
                "timestamp UNINDEXED, "
                "text, "
                'tokenize="unicode61 remove_diacritics 1"'
                ");"
                "CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions "
                "BEGIN "
                "DELETE FROM sessions_fts WHERE session_key = old.session_key; "
                "END;"
            )
            # Additive migrations
            try:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN session_started_at TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN last_interaction_at TEXT NOT NULL DEFAULT ''"
                )
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN created_actor TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN model_ref TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE sessions ADD COLUMN agent_runtime TEXT")
            except sqlite3.OperationalError:
                pass
            conn.commit()
            self._schema_ensured = True

    def rollover(self, session_key: str) -> None:
        """Rollover an existing session (rename key to archived)."""
        import asyncio

        async def _body() -> None:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT session_key FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                if row:
                    archived_key = f"{session_key}_archived_{_now_iso().replace(':', '')}"
                    conn.execute(
                        "UPDATE sessions SET session_key = ? WHERE session_key = ?",
                        (archived_key, session_key),
                    )
                    conn.commit()
            except sqlite3.Error:
                pass
            finally:
                conn.close()

        asyncio.run(_body())

    def _row_to_record(self, row: sqlite3.Row) -> SessionRecord:
        """Map a ``sessions`` row to a ``SessionRecord``."""
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
            session_started_at=row["session_started_at"],
            last_interaction_at=row["last_interaction_at"],
            created_actor=row["created_actor"],
            parent_session_key=row["parent_session_key"],
            thread_id=row["thread_id"],
            entries=tuple(entries_list),
            model_ref=row["model_ref"],
            agent_runtime=row["agent_runtime"],
        )

    def get(self, session_key: str) -> Optional[SessionRecord]:
        """Read one session by key."""
        import asyncio

        async def _body() -> Optional[SessionRecord]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT session_key, agent_id, kind, created_at, "
                    "updated_at, session_started_at, last_interaction_at, "
                    "created_actor, parent_session_key, thread_id, "
                    "entries_json, model_ref, agent_runtime "
                    "FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                if row is None:
                    return None
                return self._row_to_record(row)
            finally:
                conn.close()

        return asyncio.run(_body())

    def set_route_pin(
        self,
        session_key: str,
        *,
        model_ref: str | None = None,
        agent_runtime: str | None = None,
    ) -> Optional[SessionRecord]:
        """Record (or clear) the session's route pin."""
        import asyncio

        async def _body() -> Optional[SessionRecord]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        "SELECT session_key FROM sessions WHERE session_key = ?",
                        (session_key,),
                    ).fetchone()
                    if row is None:
                        conn.rollback()
                        return None
                    conn.execute(
                        "UPDATE sessions SET model_ref = ?, agent_runtime = ?, "
                        "updated_at = ? WHERE session_key = ?",
                        (model_ref, agent_runtime, _now_iso(), session_key),
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                row = conn.execute(
                    "SELECT session_key, agent_id, kind, created_at, "
                    "updated_at, session_started_at, last_interaction_at, "
                    "created_actor, parent_session_key, thread_id, "
                    "entries_json, model_ref, agent_runtime "
                    "FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                assert row is not None
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
        thread_id: str | None = None,
        created_actor: str | None = None,
    ) -> SessionRecord:
        """Get the existing session or create a new one."""
        import asyncio

        async def _body() -> SessionRecord:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                now = _now_iso()
                conn.execute(
                    "INSERT OR IGNORE INTO sessions ("
                    "session_key, agent_id, kind, created_at, updated_at, "
                    "session_started_at, last_interaction_at, "
                    "created_actor, parent_session_key, thread_id, entries_json, "
                    "model_ref, agent_runtime) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', NULL, NULL)",
                    (
                        session_key,
                        agent_id,
                        kind,
                        now,
                        now,
                        now,
                        now,
                        created_actor,
                        parent_session_key,
                        thread_id,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT session_key, agent_id, kind, created_at, "
                    "updated_at, session_started_at, last_interaction_at, "
                    "created_actor, parent_session_key, thread_id, "
                    "entries_json, model_ref, agent_runtime "
                    "FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                assert row is not None
                return self._row_to_record(row)
            finally:
                conn.close()

        return asyncio.run(_body())

    def append_entry(self, session_key: str, entry: dict[str, Any]) -> SessionRecord:
        """Append ``entry`` to the session's transcript."""
        import asyncio

        async def _body() -> SessionRecord:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                conn.execute("BEGIN IMMEDIATE")
                try:
                    row = conn.execute(
                        "SELECT entries_json FROM sessions WHERE session_key = ?",
                        (session_key,),
                    ).fetchone()
                    if row is None:
                        raise KeyError(
                            f"session_key {session_key!r} not found; call get_or_create first"
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
                        "UPDATE sessions SET entries_json = ?, updated_at = ?, last_interaction_at = ? "
                        "WHERE session_key = ?",
                        (
                            json.dumps(entries_list, separators=(",", ":")),
                            now,
                            now,
                            session_key,
                        ),
                    )

                    if entry.get("kind") in ("user_message", "assistant_message"):
                        payload = entry.get("payload")
                        text = payload.get("text", "") if isinstance(payload, dict) else ""
                        if text:
                            role = "user" if entry["kind"] == "user_message" else "assistant"
                            conn.execute(
                                "INSERT INTO sessions_fts(session_key, role, timestamp, text) VALUES (?, ?, ?, ?)",
                                (session_key, role, now, text),
                            )

                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
                # Re-read for the return value.
                row = conn.execute(
                    "SELECT session_key, agent_id, kind, created_at, "
                    "updated_at, session_started_at, last_interaction_at, "
                    "created_actor, parent_session_key, thread_id, "
                    "entries_json, model_ref, agent_runtime "
                    "FROM sessions WHERE session_key = ?",
                    (session_key,),
                ).fetchone()
                assert row is not None
                return self._row_to_record(row)
            finally:
                conn.close()

        return asyncio.run(_body())

    def list_sessions(self, agent_id: Optional[str] = None) -> list[SessionRecord]:
        """Return every session, optionally filtered by ``agent_id``."""
        import asyncio

        async def _body() -> list[SessionRecord]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                if agent_id is None:
                    rows = conn.execute(
                        "SELECT session_key, agent_id, kind, created_at, "
                        "updated_at, session_started_at, last_interaction_at, "
                        "created_actor, parent_session_key, thread_id, "
                        "entries_json, model_ref, agent_runtime "
                        "FROM sessions ORDER BY created_at ASC"
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT session_key, agent_id, kind, created_at, "
                        "updated_at, session_started_at, last_interaction_at, "
                        "created_actor, parent_session_key, thread_id, "
                        "entries_json, model_ref, agent_runtime "
                        "FROM sessions "
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

    def search_sessions(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        import asyncio

        async def _body() -> list[dict[str, Any]]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                rows = conn.execute(
                    "SELECT session_key, role, timestamp, snippet(sessions_fts, 3, '\x02', '\x03', '...', 64) as excerpt "
                    "FROM sessions_fts WHERE text MATCH ? ORDER BY timestamp DESC LIMIT ?",
                    (query, limit),
                ).fetchall()
                results: list[dict[str, Any]] = []
                for row in rows:
                    results.append(
                        {
                            "session_key": row["session_key"],
                            "role": row["role"],
                            "timestamp": row["timestamp"],
                            "excerpt": row["excerpt"],
                        }
                    )
                return results
            finally:
                conn.close()

        return asyncio.run(_body())


__all__ = [
    "InMemorySessionStore",
    "SQLITE_SESSIONS_SCHEMA_SQL",
    "SessionRecord",
    "SessionStore",
    "SqliteSessionStore",
    "get_default_session_store",
    "reset_default_session_store",
]
