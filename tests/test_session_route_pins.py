"""Tests for session route pins (model_ref + agent_runtime).

Pins record the resolved route owning a session's turns so future
doctor passes can repair stale ones. Additive-only storage: new
nullable columns, old rows read back unpinned, no schema-version bump.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.sessions.session_store import (
    InMemorySessionStore,
    SessionRecord,
    SqliteSessionStore,
)


def _factory(tmp_path: Path):
    db_path = tmp_path / "state.sqlite"
    db_path.touch()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    return factory


def test_record_defaults_unpinned():
    rec = SessionRecord(
        session_key="k", agent_id="a", kind="direct", created_at="t", updated_at="t"
    )
    assert rec.model_ref is None
    assert rec.agent_runtime is None


def test_in_memory_pin_lifecycle():
    store = InMemorySessionStore()
    assert store.set_route_pin("missing", model_ref="openai/x") is None
    store.get_or_create(session_key="k", agent_id="a", kind="direct")
    pinned = store.set_route_pin("k", model_ref="openai/gpt-5.6-sol", agent_runtime="codex")
    assert pinned is not None
    assert (pinned.model_ref, pinned.agent_runtime) == ("openai/gpt-5.6-sol", "codex")
    assert store.get("k").model_ref == "openai/gpt-5.6-sol"
    cleared = store.set_route_pin("k")
    assert cleared is not None
    assert (cleared.model_ref, cleared.agent_runtime) == (None, None)


def test_in_memory_preserves_pins_across_writes():
    store = InMemorySessionStore()
    store.get_or_create(session_key="k", agent_id="a", kind="direct")
    store.set_route_pin("k", model_ref="openai/x", agent_runtime="codex")
    store.append_entry("k", {"id": "e1", "kind": "user_message", "payload": {"text": "hi"}})
    assert store.get("k").model_ref == "openai/x"
    store.rollover("k")
    archived = [s for s in store.list_sessions() if "archived" in s.session_key]
    assert len(archived) == 1
    assert (archived[0].model_ref, archived[0].agent_runtime) == ("openai/x", "codex")


def test_sqlite_pin_round_trip(tmp_path: Path) -> None:
    store = SqliteSessionStore(connection_factory=_factory(tmp_path))
    store.get_or_create(session_key="k", agent_id="a", kind="direct")
    assert store.get("k").model_ref is None
    pinned = store.set_route_pin("k", model_ref="openai/gpt-5.6-sol", agent_runtime="codex")
    assert pinned is not None
    assert (pinned.model_ref, pinned.agent_runtime) == ("openai/gpt-5.6-sol", "codex")
    assert store.get("k").agent_runtime == "codex"
    assert store.list_sessions()[0].model_ref == "openai/gpt-5.6-sol"
    assert store.set_route_pin("missing") is None


def test_sqlite_migrates_legacy_rows_unpinned(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE sessions (session_key TEXT PRIMARY KEY, agent_id TEXT NOT NULL, "
        "kind TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "parent_session_key TEXT, thread_id TEXT, entries_json TEXT NOT NULL DEFAULT '[]')"
    )
    conn.execute(
        "INSERT INTO sessions (session_key, agent_id, kind, created_at, updated_at) "
        "VALUES ('legacy', 'a', 'direct', 't', 't')"
    )
    conn.commit()
    conn.close()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    store = SqliteSessionStore(connection_factory=factory)
    record = store.get("legacy")
    assert record is not None
    assert (record.model_ref, record.agent_runtime) == (None, None)
    # ...and pins become writable on the migrated row.
    assert store.set_route_pin("legacy", model_ref="openai/x") is not None
    assert store.get("legacy").model_ref == "openai/x"
