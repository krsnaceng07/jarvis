"""Canonical state database for the JARVIS Brain Core.

Mirrors a focused subset of OpenClaw's
``src/state/openclaw-state-db.ts`` (the connection
factory + transaction runner + readonly helpers). The
heavy schema + audit-migration code is a follow-up
commit; the Python port focuses on:

- the ``StateDatabase`` context (connection factory +
  readonly + busy-timeout helpers)
- the ``run_write_transaction`` runner that wraps a
  callback in a per-store-path serialization queue
  (mirrors ``runExclusiveSessionStoreWrite``)
- the ``run_queued_store_write`` runner that serializes
  work per-key within a single process
- the Kysely-like ``Query`` helper that takes a connection
  + a list of table names and returns a fluent
  ``SELECT``/``INSERT``/``UPDATE``/``DELETE`` builder
  (the Python port uses direct ``sqlite3`` SQL with
  placeholder escaping)

Public surface (mirrors the TS source):
- ``StateDatabase`` — the context that opens a
  connection per call and routes to a per-store-path
  FIFO queue
- ``run_write_transaction`` — wrap a callback in a
  per-store-path FIFO write transaction
- ``run_queued_store_write`` — wrap a callback in a
  per-key FIFO queue
- ``Query`` — the fluent SELECT/INSERT/UPDATE/DELETE
  builder
- ``StateDatabaseOptions`` — the DI bag (connection
  factory, env, path, now override)

Python adaptations (documented in code):
- TS Kysely → direct ``sqlite3`` SQL. The Query helper
  exposes a fluent builder for the common cases; advanced
  queries use raw ``conn.execute(sql, params)``.
- TS AsyncLocalStorage → Python ``contextvars.ContextVar``
  (the active-writer reentrancy context)
- TS ``Map`` → Python ``dict``
- TS ``setTimeout(..., unref)`` → Python
  ``threading.Timer`` (daemon, fire-and-forget)
"""
from __future__ import annotations

import contextvars
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── State ─────────────────────────────────────────────────


@dataclass
class _FifoQueue:
    """Per-key FIFO queue that serializes async tasks within one process.

    Mirrors the shape of OpenClaw's ``StoreWriterQueue``.
    """

    running: bool = False
    pending: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _State:
    queues: dict[str, _FifoQueue] = field(default_factory=dict)


_state_lock = threading.Lock()
_state: _State = _State()


def _get_or_create_queue(queues: dict[str, _FifoQueue], key: str) -> _FifoQueue:
    queue = queues.get(key)
    if queue is None:
        queue = _FifoQueue()
        queues[key] = queue
    return queue


# ── Active-writer reentrancy context ─────────────────────


@dataclass
class _ActiveWriter:
    active: bool
    parent: Optional["_ActiveWriter"]
    queues_id: int
    key: str


_active_writer_var: contextvars.ContextVar[Optional[_ActiveWriter]] = (
    contextvars.ContextVar("jarvis.stateCore.activeWriter", default=None)
)


def _is_reentrant(queues_id: int, key: str) -> bool:
    active = _active_writer_var.get()
    while active is not None:
        if (
            active.active
            and active.queues_id == queues_id
            and active.key == key
        ):
            return True
        active = active.parent
    return False


# ── StateDatabase + options ──────────────────────────────


@dataclass
class StateDatabaseOptions:
    """Configuration bag for ``StateDatabase`` + the runners.

    Mirrors OpenClaw's ``OpenClawStateDatabaseOptions`` plus
    the per-call ``now`` override. The factory is called
    fresh per open so callers can use a per-test temp DB
    or the canonical state DB at
    ``~/.jarvis/state/jarvis.sqlite``.
    """

    connection_factory: Optional[Callable[[], sqlite3.Connection]] = None
    env: Optional[dict[str, str]] = None
    path: Optional[str] = None
    now: Optional[int] = None
    busy_timeout_ms: int = 5_000


class StateDatabase:
    """Canonical state database for the JARVIS Brain Core.

    Mirrors a focused subset of OpenClaw's
    ``openclaw-state-db.ts``. The class is a thin
    connection-opener + transaction runner; the heavy
    schema (61K DDL) lands in a follow-up commit.
    """

    def __init__(self, options: Optional[StateDatabaseOptions] = None) -> None:
        self.options = options or StateDatabaseOptions()
        self._queues_id = id(self._queues_for(self))

    def open(self) -> sqlite3.Connection:
        """Open a new connection with the standard pragmas applied.

        Mirrors ``openOpenClawStateDatabase``. The factory
        is called fresh each time so per-test temp DBs
        stay isolated.
        """
        if self.options.connection_factory is None:
            raise ValueError(
                "StateDatabase: connection_factory is required "
                "(host must wire the canonical state DB)"
            )
        conn = self.options.connection_factory()
        conn.row_factory = sqlite3.Row
        # Apply the standard pragmas. ``busy_timeout`` is
        # critical for SQLite write contention; the default
        # 5s matches OpenClaw's
        # ``SESSION_STATE_SQLITE_BUSY_TIMEOUT_MS``.
        timeout = self.options.busy_timeout_ms
        if timeout > 0:
            conn.execute(f"PRAGMA busy_timeout = {int(timeout)}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _queues_for(self, _db: "StateDatabase") -> dict[str, _FifoQueue]:
        """Return the per-instance FIFO queue map.

        Mirrors the OpenClaw singleton that routes
        per-store-path writes through a single queue map.
        """
        # Use the singleton so multiple StateDatabase
        # instances share the same per-process queue map
        # (matches the OpenClaw "shared state" semantics).
        return _state.queues

    def queues_id(self) -> int:
        return self._queues_id

    def path(self) -> str:
        """Return the canonical state DB path."""
        if self.options.path:
            return self.options.path
        env = self.options.env or {}
        env_path = env.get("JARVIS_STATE_DIR")
        base = env_path or os.path.join(
            os.path.expanduser("~"), ".jarvis", "state"
        )
        return os.path.join(base, "jarvis.sqlite")


# ── Queued store write ────────────────────────────────────


async def _drain_queue(queues: dict[str, _FifoQueue], key: str) -> None:
    queue = queues.get(key)
    if queue is None:
        return
    try:
        while queue.pending:
            task = queue.pending.pop(0)
            writer = _ActiveWriter(
                active=True,
                parent=_active_writer_var.get(),
                queues_id=id(queues),
                key=key,
            )
            token = _active_writer_var.set(writer)
            try:
                result = await task["fn"]()
                if not task["future"].done():
                    task["future"].set_result(result)
            except Exception as error:  # noqa: BLE001
                if not task["future"].done():
                    task["future"].set_exception(error)
            finally:
                _active_writer_var.reset(token)
    finally:
        queue.running = False


async def run_queued_store_write(
    *,
    queues: dict[str, _FifoQueue],
    key: str,
    label: str,
    fn: Callable[[], Any],
    reentrant: bool = True,
) -> Any:
    """Run ``fn`` under the per-key FIFO queue.

    Mirrors ``runQueuedStoreWrite`` from
    ``@openclaw/shared/store-writer-queue``. ``reentrant=True``
    lets a writer call the same lane again without re-queuing.
    """
    import asyncio

    if reentrant and _is_reentrant(id(queues), key):
        return await fn()
    queue = _get_or_create_queue(queues, key)
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    queue.pending.append({"fn": fn, "future": future})
    if not queue.running:
        queue.running = True
        try:
            await _drain_queue(queues, key)
        finally:
            queue.running = False
    return await future


# ── Write transaction ────────────────────────────────────


async def run_write_transaction(
    db: StateDatabase,
    *,
    store_path: Optional[str] = None,
    fn: Callable[[sqlite3.Connection], Any],
    reentrant: bool = True,
) -> Any:
    """Run ``fn`` under the per-store-path FIFO write transaction.

    Mirrors ``runExclusiveSessionStoreWrite``. The
    callback receives a ``sqlite3.Connection`` that's
    wired to the canonical state DB; the helper uses
    ``BEGIN IMMEDIATE`` to acquire the write lock early
    and ``COMMIT`` / ``ROLLBACK`` to settle the
    transaction.
    """
    if db.options.connection_factory is None:
        raise ValueError(
            "run_write_transaction: connection_factory is required"
        )
    key = store_path or db.path()

    async def _body() -> Any:
        conn = db.open()
        try:
            # ``BEGIN IMMEDIATE`` acquires the write lock
            # at BEGIN time so concurrent writers wait
            # outside the transaction (rather than
            # ``SQLITE_BUSY`` mid-insert).
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = await fn(conn)
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()

    return await run_queued_store_write(
        queues=db._queues_for(db),
        key=key,
        label="runExclusiveStateStoreWrite",
        fn=_body,
        reentrant=reentrant,
    )


# ── Query helper (Kysely-like) ───────────────────────────


class Query:
    """Fluent SELECT/INSERT/UPDATE/DELETE builder.

    Mirrors a tiny subset of OpenClaw's Kysely builder. The
    Python port exposes the most common cases (select /
    insert / update / delete + where / order by / limit /
    returning) on top of direct ``sqlite3`` SQL.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def select(self, *columns: str) -> "SelectBuilder":
        if not columns:
            columns = ("*",)
        return SelectBuilder(self._conn, list(columns))

    def insert_into(self, table: str) -> "InsertBuilder":
        return InsertBuilder(self._conn, table)

    def update_table(self, table: str) -> "UpdateBuilder":
        return UpdateBuilder(self._conn, table)

    def delete_from(self, table: str) -> "DeleteBuilder":
        return DeleteBuilder(self._conn, table)


class _BaseBuilder:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._where: list[tuple[str, list[Any]]] = []

    def where(self, column: str, value: Any) -> "_BaseBuilder":
        self._where.append((f"{column} = ?", [value]))
        return self

    def where_in(self, column: str, values: list[Any]) -> "_BaseBuilder":
        if not values:
            # An empty IN clause matches nothing; we use a
            # marker so the SQL stays well-formed.
            self._where.append(("1=0", []))
            return self
        placeholders = ",".join("?" for _ in values)
        self._where.append((f"{column} IN ({placeholders})", list(values)))
        return self


class SelectBuilder(_BaseBuilder):
    def __init__(self, conn: sqlite3.Connection, columns: list[str]) -> None:
        super().__init__(conn)
        self._columns = columns
        self._table: Optional[str] = None
        self._order_by: list[str] = []
        self._limit: Optional[int] = None
        self._distinct: bool = False

    def from_table(self, table: str) -> "SelectBuilder":
        self._table = table
        return self

    def distinct(self) -> "SelectBuilder":
        self._distinct = True
        return self

    def order_by(self, column: str, direction: str = "asc") -> "SelectBuilder":
        self._order_by.append(f"{column} {direction.upper()}")
        return self

    def limit(self, n: int) -> "SelectBuilder":
        self._limit = n
        return self

    def execute(self) -> list[sqlite3.Row]:
        if self._table is None:
            raise ValueError("select: from_table is required")
        cols = ", ".join(self._columns)
        distinct = "DISTINCT " if self._distinct else ""
        sql = f"SELECT {distinct}{cols} FROM {self._table}"
        params: list[Any] = []
        for clause, vals in self._where:
            sql += f" WHERE {clause}"
            params.extend(vals)
        if self._order_by:
            sql += " ORDER BY " + ", ".join(self._order_by)
        if self._limit is not None:
            sql += f" LIMIT {int(self._limit)}"
        cursor = self._conn.execute(sql, params)
        return cursor.fetchall()

    def execute_take_first(self) -> Optional[sqlite3.Row]:
        rows = self.execute()
        return rows[0] if rows else None


class InsertBuilder(_BaseBuilder):
    def __init__(self, conn: sqlite3.Connection, table: str) -> None:
        super().__init__(conn)
        self._table = table
        self._values: dict[str, Any] = {}

    def values(self, **kwargs: Any) -> "InsertBuilder":
        self._values.update(kwargs)
        return self

    def on_conflict(self, action: str = "do_nothing") -> "InsertBuilder":
        self._conflict_action = action
        return self

    def execute(self) -> sqlite3.Cursor:
        if not self._values:
            raise ValueError("insert: values are required")
        columns = list(self._values.keys())
        placeholders = ",".join("?" for _ in columns)
        params = [self._values[c] for c in columns]
        sql = f"INSERT INTO {self._table} ({','.join(columns)}) VALUES ({placeholders})"
        conflict = getattr(self, "_conflict_action", None)
        if conflict == "do_nothing":
            sql += " ON CONFLICT DO NOTHING"
        elif conflict == "do_update_set":
            sql += " ON CONFLICT DO UPDATE SET "
            # Caller sets a special attribute for update set.
            update_set = getattr(self, "_update_set", None) or []
            sql += ", ".join(update_set)
        return self._conn.execute(sql, params)


class UpdateBuilder(_BaseBuilder):
    def __init__(self, conn: sqlite3.Connection, table: str) -> None:
        super().__init__(conn)
        self._table = table
        self._set: dict[str, Any] = {}

    def set(self, column: str, value: Any) -> "UpdateBuilder":
        self._set[column] = value
        return self

    def execute(self) -> sqlite3.Cursor:
        if not self._set:
            raise ValueError("update: set is required")
        set_clauses = ", ".join(f"{col} = ?" for col in self._set.keys())
        params: list[Any] = list(self._set.values())
        sql = f"UPDATE {self._table} SET {set_clauses}"
        for clause, vals in self._where:
            sql += f" WHERE {clause}"
            params.extend(vals)
        return self._conn.execute(sql, params)


class DeleteBuilder(_BaseBuilder):
    def __init__(self, conn: sqlite3.Connection, table: str) -> None:
        super().__init__(conn)
        self._table = table

    def execute(self) -> sqlite3.Cursor:
        sql = f"DELETE FROM {self._table}"
        params: list[Any] = []
        for clause, vals in self._where:
            sql += f" WHERE {clause}"
            params.extend(vals)
        return self._conn.execute(sql, params)


# ── Bootstrap helper ────────────────────────────────────


def ensure_schema(
    conn: sqlite3.Connection,
    *,
    schema_sql: Optional[str] = None,
) -> None:
    """Run the given (or default) ``CREATE TABLE IF NOT EXISTS`` SQL.

    Used by feature modules to lazily bootstrap their
    per-feature tables. The default ``schema_sql`` is the
    union of the JARVIS Brain Core baseline (state events
    + heads + watch cursors + upstream links + lease).
    """
    if schema_sql is None:
        schema_sql = (
            # State events (session_state_events.py)
            "CREATE TABLE IF NOT EXISTS session_state_events ("
            "sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
            "session_key TEXT NOT NULL, "
            "session_id TEXT, "
            "agent_id TEXT NOT NULL, "
            "kind TEXT NOT NULL, "
            "actor_type TEXT NOT NULL, "
            "actor_id TEXT, "
            "run_id TEXT, "
            "dedupe_key TEXT, "
            "occurred_at INTEGER NOT NULL, "
            "recorded_at INTEGER NOT NULL, "
            "summary TEXT NOT NULL, "
            "payload_json TEXT"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_session_state_events_session "
            "ON session_state_events (session_key, sequence);"
            # State heads
            "CREATE TABLE IF NOT EXISTS session_state_heads ("
            "session_key TEXT PRIMARY KEY, "
            "version INTEGER NOT NULL, "
            "updated_at INTEGER NOT NULL"
            ");"
            # Watch cursors
            "CREATE TABLE IF NOT EXISTS session_watch_cursors ("
            "target_session_key TEXT NOT NULL, "
            "watcher_session_key TEXT NOT NULL, "
            "provenance TEXT NOT NULL, "
            "last_delivered_at INTEGER, "
            "created_at INTEGER NOT NULL, "
            "PRIMARY KEY (target_session_key, watcher_session_key)"
            ");"
            # Upstream links (session_upstream_links.py)
            "CREATE TABLE IF NOT EXISTS session_upstream_links ("
            "session_key TEXT NOT NULL, "
            "agent_id TEXT NOT NULL, "
            "catalog_id TEXT NOT NULL, "
            "host_id TEXT NOT NULL, "
            "thread_id TEXT NOT NULL, "
            "upstream_kind TEXT NOT NULL, "
            "upstream_ref_json TEXT NOT NULL, "
            "last_marker_json TEXT, "
            "last_scanned_at INTEGER, "
            "created_at INTEGER NOT NULL, "
            "updated_at INTEGER NOT NULL, "
            "PRIMARY KEY (session_key, agent_id)"
            ");"
            "CREATE INDEX IF NOT EXISTS idx_session_upstream_links_catalog "
            "ON session_upstream_links (catalog_id);"
            # State leases
            "CREATE TABLE IF NOT EXISTS state_lease_owners ("
            "owner_id TEXT PRIMARY KEY, "
            "fence INTEGER NOT NULL, "
            "acquired_at INTEGER NOT NULL, "
            "expires_at INTEGER NOT NULL"
            ");"
            # Pairing
            "CREATE TABLE IF NOT EXISTS channel_pairing_requests ("
            "channel TEXT NOT NULL, "
            "account_id TEXT NOT NULL, "
            "sender_id TEXT NOT NULL, "
            "pairing_code TEXT NOT NULL, "
            "created_at INTEGER NOT NULL, "
            "expires_at INTEGER NOT NULL, "
            "PRIMARY KEY (channel, account_id, sender_id)"
            ");"
            "CREATE TABLE IF NOT EXISTS channel_pairing_allow_entries ("
            "channel TEXT NOT NULL, "
            "account_id TEXT NOT NULL, "
            "sender_id TEXT NOT NULL, "
            "approved_at INTEGER NOT NULL, "
            "PRIMARY KEY (channel, account_id, sender_id)"
            ");"
        )
    conn.executescript(schema_sql)
    conn.commit()


def reset_state_for_tests() -> None:
    """Clear the singleton state. Test-only helper."""
    global _state
    with _state_lock:
        _state = _State()


__all__ = [
    "DeleteBuilder",
    "InsertBuilder",
    "Query",
    "SelectBuilder",
    "StateDatabase",
    "StateDatabaseOptions",
    "UpdateBuilder",
    "ensure_schema",
    "reset_state_for_tests",
    "run_queued_store_write",
    "run_write_transaction",
]
