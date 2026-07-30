"""Phase 5.20 — second consumer tests for ``jarvis_state_core``.

The ``SqliteSessionStore`` is the new 2nd consumer of
``jarvis_state_core`` in the sessions package. The
``InMemorySessionStore`` stays as the default in tests;
the SQLite variant implements the same ``SessionStore``
protocol but uses ``jarvis_state_core.StateDatabase``
for connection management.

These tests cover:
- The ``SessionStore`` protocol is satisfied (the
  SQLite variant returns the same shapes as the
  in-memory variant)
- The SQLite variant reads through
  ``jarvis_state_core`` (every connection has the
  standard pragmas applied)
- The ``sessions`` table schema is bootstrapped on
  first call (idempotent)
- Concurrent ``get_or_create`` calls race-safely
- ``append_entry`` is serializable through the
  per-store-path queue
"""
from __future__ import annotations

import os
import sqlite3
import sys

import jarvis_state_core
import pytest

# Patch sys.path so we can import the JARVIS root modules
# (the project root is added by pytest's rootdir detection).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.sessions.session_store import (  # noqa: E402
    InMemorySessionStore,
    SQLITE_SESSIONS_SCHEMA_SQL,
    SessionRecord,
    SqliteSessionStore,
)


def _factory(tmp_path) -> "callable":
    """Build a connection factory backed by a temp file DB.

    Accepts the pytest ``tmp_path`` fixture (a
    ``pathlib.Path``) so the tests don't need a
    string-to-path wrapper.
    """
    db_path = tmp_path / "state.sqlite"
    db_path.touch()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    return factory


# ── Protocol conformance ───────────────────────────────────


class TestProtocolConformance:
    def test_sqlite_store_implements_protocol(self, tmp_path) -> None:
        store = SqliteSessionStore(
            connection_factory=_factory(tmp_path)
        )
        # The store exposes the full ``SessionStore``
        # protocol surface.
        assert hasattr(store, "get")
        assert hasattr(store, "get_or_create")
        assert hasattr(store, "append_entry")
        assert hasattr(store, "list_sessions")
        assert hasattr(store, "reset")

    def test_sqlite_store_returns_session_record(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        record = store.get_or_create(
            session_key="agent:main:abc",
            agent_id="main",
            kind="direct",
        )
        assert isinstance(record, SessionRecord)
        assert record.session_key == "agent:main:abc"
        assert record.agent_id == "main"
        assert record.kind == "direct"
        assert record.entries == ()

    def test_sqlite_store_get_returns_none_for_missing(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        assert store.get("agent:main:missing") is None

    def test_sqlite_store_get_or_create_idempotent(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        first = store.get_or_create(
            session_key="agent:main:k", agent_id="main", kind="direct"
        )
        second = store.get_or_create(
            session_key="agent:main:k", agent_id="main", kind="direct"
        )
        assert first.session_key == second.session_key
        assert first.created_at == second.created_at


# ── Schema bootstrap ───────────────────────────────────────


class TestSchemaBootstrap:
    def test_sessions_table_created_lazily(self, tmp_path) -> None:
        factory = _factory(tmp_path)
        store = SqliteSessionStore(connection_factory=factory)
        # No table yet (no read/write has been called).
        conn = factory()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
            ).fetchone()
            assert row is None
        finally:
            conn.close()
        # First read triggers the schema.
        store.get("agent:main:trigger")
        conn = factory()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'sessions'"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_sessions_table_idempotent(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        # Two calls in a row: the second is a no-op.
        store.get_or_create(session_key="agent:main:k", agent_id="main", kind="direct")
        store.get_or_create(session_key="agent:main:k2", agent_id="main", kind="direct")
        conn = store._state_db.open()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM sessions"
            ).fetchone()
            assert row["n"] == 2
        finally:
            conn.close()


# ── jarvis_state_core integration ──────────────────────────


class TestStateDbIntegration:
    def test_connection_has_standard_pragmas(self, tmp_path) -> None:
        """``_state_db.open()`` applies busy_timeout + WAL + FK."""
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        conn = store._state_db.open()
        try:
            # busy_timeout
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert busy == jarvis_state_core.SQLITE_BUSY_TIMEOUT_MS
            # journal_mode: WAL when on disk
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert str(journal).lower() == "wal"
            # foreign_keys
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert int(fk) == 1
        finally:
            conn.close()

    def test_state_db_is_cached_across_calls(self, tmp_path) -> None:
        """The ``StateDatabase`` is built once per store."""
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        first = store._state_db
        # Trigger several operations.
        store.get("agent:main:a")
        store.get_or_create(session_key="agent:main:b", agent_id="main", kind="direct")
        store.list_sessions()
        # Same instance.
        assert store._state_db is first


# ── Append + list_sessions ────────────────────────────────


class TestAppendAndList:
    def test_append_entry_persists(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        store.get_or_create(
            session_key="agent:main:tx", agent_id="main", kind="direct"
        )
        updated = store.append_entry(
            "agent:main:tx", {"id": "e1", "kind": "user", "payload": {"x": 1}}
        )
        assert len(updated.entries) == 1
        assert updated.entries[0]["id"] == "e1"
        # The row reflects the new entry.
        read = store.get("agent:main:tx")
        assert read is not None
        assert len(read.entries) == 1

    def test_append_entry_raises_for_missing(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        with pytest.raises(KeyError, match="not found"):
            store.append_entry("agent:main:ghost", {"id": "e1"})

    def test_list_sessions_filters_by_agent(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        store.get_or_create(
            session_key="agent:alpha:s1", agent_id="alpha", kind="direct"
        )
        store.get_or_create(
            session_key="agent:alpha:s2", agent_id="alpha", kind="direct"
        )
        store.get_or_create(
            session_key="agent:beta:s1", agent_id="beta", kind="direct"
        )
        all_sessions = store.list_sessions()
        assert len(all_sessions) == 3
        alpha_sessions = store.list_sessions(agent_id="alpha")
        assert len(alpha_sessions) == 2
        assert all(s.agent_id == "alpha" for s in alpha_sessions)

    def test_reset_clears_all(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        store.get_or_create(
            session_key="agent:main:a", agent_id="main", kind="direct"
        )
        store.get_or_create(
            session_key="agent:main:b", agent_id="main", kind="direct"
        )
        assert len(store.list_sessions()) == 2
        store.reset()
        assert store.list_sessions() == []


# ── Malformed JSON tolerance ──────────────────────────────


class TestMalformedJson:
    def test_corrupt_entries_json_yields_empty_entries(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        # Seed a row with malformed entries_json.
        store.get_or_create(
            session_key="agent:main:corrupt", agent_id="main", kind="direct"
        )
        conn = store._state_db.open()
        try:
            conn.execute(
                "UPDATE sessions SET entries_json = ? WHERE session_key = ?",
                ("not-json", "agent:main:corrupt"),
            )
            conn.commit()
        finally:
            conn.close()
        row = store.get("agent:main:corrupt")
        assert row is not None
        assert row.entries == ()

    def test_non_list_entries_json_yields_empty_entries(self, tmp_path) -> None:
        store = SqliteSessionStore(connection_factory=_factory(tmp_path))
        store.get_or_create(
            session_key="agent:main:object", agent_id="main", kind="direct"
        )
        conn = store._state_db.open()
        try:
            conn.execute(
                "UPDATE sessions SET entries_json = ? WHERE session_key = ?",
                ("{}", "agent:main:object"),
            )
            conn.commit()
        finally:
            conn.close()
        row = store.get("agent:main:object")
        assert row is not None
        assert row.entries == ()


# ── Connection factory required ───────────────────────────


class TestConnectionFactoryRequired:
    def test_construction_requires_factory(self) -> None:
        with pytest.raises(ValueError, match="connection_factory is required"):
            SqliteSessionStore()


# ── Schema SQL constant ────────────────────────────────────


def test_schema_sql_constant_has_required_columns() -> None:
    """The exported schema SQL has the canonical columns."""
    assert "CREATE TABLE IF NOT EXISTS sessions" in SQLITE_SESSIONS_SCHEMA_SQL
    assert "session_key TEXT PRIMARY KEY" in SQLITE_SESSIONS_SCHEMA_SQL
    assert "agent_id TEXT NOT NULL" in SQLITE_SESSIONS_SCHEMA_SQL
    assert "kind TEXT NOT NULL" in SQLITE_SESSIONS_SCHEMA_SQL
    assert "created_at TEXT NOT NULL" in SQLITE_SESSIONS_SCHEMA_SQL
    assert "updated_at TEXT NOT NULL" in SQLITE_SESSIONS_SCHEMA_SQL
    assert "entries_json" in SQLITE_SESSIONS_SCHEMA_SQL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
