"""Tests for ``jarvis_state_core.audit_migration``.

Covers:
- legacy shape → v2 rebuild + sequence high-water restore
- canonical v2 shape is left alone
- foreign ``audit_events_migration_new`` table fails closed
- pre-migration databases (no ``audit_events`` at all) are
  treated as canonical at user_version < 2
- identity-key table is created on rebuild
"""
from __future__ import annotations

import sqlite3

import pytest

from jarvis_state_core.audit_migration import (
    AUDIT_EVENT_LEGACY_COLUMNS,
    AUDIT_EVENT_STATE_SCHEMA_VERSION,
    AUDIT_EVENT_V2_COLUMNS,
    can_repair_legacy_audit_events_schema,
    has_canonical_audit_events_schema,
    repair_audit_events_schema,
)


# ── Helpers ───────────────────────────────────────────────


_LEGACY_CREATE = """
CREATE TABLE audit_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  source_id TEXT NOT NULL UNIQUE,
  source_sequence INTEGER NOT NULL,
  occurred_at INTEGER NOT NULL,
  kind TEXT NOT NULL,
  action TEXT NOT NULL,
  status TEXT NOT NULL,
  error_code TEXT,
  actor_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  agent_id TEXT,
  session_key TEXT,
  session_id TEXT,
  run_id TEXT,
  tool_call_id TEXT,
  tool_name TEXT
);
"""


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _create_legacy_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_LEGACY_CREATE)
    # Seed two rows.
    conn.execute(
        "INSERT INTO audit_events (event_id, source_id, source_sequence, "
        "occurred_at, kind, action, status, actor_type, actor_id, agent_id, "
        "run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("e1", "s1", 1, 1000, "tool.invoke", "start", "ok", "agent", "main", "main", "r1"),
    )
    conn.execute(
        "INSERT INTO audit_events (event_id, source_id, source_sequence, "
        "occurred_at, kind, action, status, actor_type, actor_id, agent_id, "
        "run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("e2", "s2", 2, 1100, "tool.invoke", "finish", "ok", "agent", "main", "main", "r1"),
    )
    conn.commit()


def _legacy_columns(conn: sqlite3.Connection) -> list[str]:
    return [
        dict(row)["name"]
        for row in conn.execute("PRAGMA table_info(audit_events)").fetchall()
    ]


# ── Schema probes ─────────────────────────────────────────


def test_legacy_table_is_not_canonical():
    conn = _fresh_db()
    try:
        _create_legacy_table(conn)
        assert has_canonical_audit_events_schema(conn) is False
    finally:
        conn.close()


def test_pre_migration_db_with_no_audit_events_is_canonical_at_v0():
    conn = _fresh_db()
    try:
        # No audit_events table; user_version = 0 < v2.
        assert has_canonical_audit_events_schema(conn) is True
    finally:
        conn.close()


def test_canonical_v2_table_is_canonical():
    conn = _fresh_db()
    try:
        conn.executescript(
            "CREATE TABLE audit_events ("
            "  sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  event_id TEXT NOT NULL UNIQUE,"
            "  source_id TEXT NOT NULL UNIQUE,"
            "  schema_version INTEGER NOT NULL DEFAULT 1,"
            "  source_sequence INTEGER NOT NULL,"
            "  occurred_at INTEGER NOT NULL,"
            "  kind TEXT NOT NULL,"
            "  action TEXT NOT NULL,"
            "  status TEXT NOT NULL,"
            "  error_code TEXT,"
            "  actor_type TEXT NOT NULL,"
            "  actor_id TEXT NOT NULL,"
            "  agent_id TEXT,"
            "  session_key TEXT,"
            "  session_id TEXT,"
            "  run_id TEXT,"
            "  tool_call_id TEXT,"
            "  tool_name TEXT,"
            "  direction TEXT,"
            "  channel TEXT,"
            "  conversation_kind TEXT,"
            "  message_outcome TEXT,"
            "  reason_code TEXT,"
            "  delivery_kind TEXT,"
            "  failure_stage TEXT,"
            "  duration_ms INTEGER,"
            "  result_count INTEGER,"
            "  account_ref TEXT,"
            "  conversation_ref TEXT,"
            "  message_ref TEXT,"
            "  target_ref TEXT"
            ");"
            "CREATE TABLE audit_identity_keys ("
            "  id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),"
            "  key_id TEXT NOT NULL,"
            "  key BLOB NOT NULL,"
            "  created_at INTEGER NOT NULL"
            ");"
        )
        conn.commit()
        assert has_canonical_audit_events_schema(conn) is True
    finally:
        conn.close()


# ── can_repair ────────────────────────────────────────────


def test_can_repair_returns_true_for_legacy():
    conn = _fresh_db()
    try:
        _create_legacy_table(conn)
        assert can_repair_legacy_audit_events_schema(conn) is True
    finally:
        conn.close()


def test_can_repair_false_when_no_audit_table():
    conn = _fresh_db()
    try:
        assert can_repair_legacy_audit_events_schema(conn) is False
    finally:
        conn.close()


def test_can_repair_false_when_foreign_migration_table_present():
    conn = _fresh_db()
    try:
        _create_legacy_table(conn)
        conn.execute("CREATE TABLE audit_events_migration_new (n INTEGER)")
        conn.commit()
        assert can_repair_legacy_audit_events_schema(conn) is False
    finally:
        conn.close()


def test_can_repair_false_when_schema_version_column_already_exists():
    conn = _fresh_db()
    try:
        # Add schema_version to legacy table; this is the
        # half-applied case we refuse to migrate further.
        _create_legacy_table(conn)
        conn.execute("ALTER TABLE audit_events ADD COLUMN schema_version INTEGER")
        conn.commit()
        assert can_repair_legacy_audit_events_schema(conn) is False
    finally:
        conn.close()


# ── Repair ────────────────────────────────────────────────


def test_repair_migrates_legacy_to_v2():
    conn = _fresh_db()
    try:
        _create_legacy_table(conn)
        applied = repair_audit_events_schema(conn)
        assert applied is True
        assert tuple(_legacy_columns(conn)) == AUDIT_EVENT_V2_COLUMNS
        # Identity keys table created.
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_identity_keys'"
        ).fetchone()
        assert row is not None
        # Rows preserved.
        rows = conn.execute(
            "SELECT event_id, source_id, schema_version, source_sequence "
            "FROM audit_events ORDER BY source_sequence"
        ).fetchall()
        assert [dict(r)["event_id"] for r in rows] == ["e1", "e2"]
        assert [dict(r)["schema_version"] for r in rows] == [1, 1]
    finally:
        conn.close()


def test_repair_is_noop_on_canonical():
    conn = _fresh_db()
    try:
        conn.executescript(
            "CREATE TABLE audit_events ("
            "  sequence INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  event_id TEXT NOT NULL UNIQUE,"
            "  source_id TEXT NOT NULL UNIQUE,"
            "  schema_version INTEGER NOT NULL DEFAULT 1,"
            "  source_sequence INTEGER NOT NULL,"
            "  occurred_at INTEGER NOT NULL,"
            "  kind TEXT NOT NULL,"
            "  action TEXT NOT NULL,"
            "  status TEXT NOT NULL,"
            "  error_code TEXT,"
            "  actor_type TEXT NOT NULL,"
            "  actor_id TEXT NOT NULL,"
            "  agent_id TEXT,"
            "  session_key TEXT,"
            "  session_id TEXT,"
            "  run_id TEXT,"
            "  tool_call_id TEXT,"
            "  tool_name TEXT,"
            "  direction TEXT,"
            "  channel TEXT,"
            "  conversation_kind TEXT,"
            "  message_outcome TEXT,"
            "  reason_code TEXT,"
            "  delivery_kind TEXT,"
            "  failure_stage TEXT,"
            "  duration_ms INTEGER,"
            "  result_count INTEGER,"
            "  account_ref TEXT,"
            "  conversation_ref TEXT,"
            "  message_ref TEXT,"
            "  target_ref TEXT"
            ");"
            "CREATE TABLE audit_identity_keys ("
            "  id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),"
            "  key_id TEXT NOT NULL,"
            "  key BLOB NOT NULL,"
            "  created_at INTEGER NOT NULL"
            ");"
        )
        conn.commit()
        assert repair_audit_events_schema(conn) is False
    finally:
        conn.close()


def test_repair_refuses_when_unsafe():
    conn = _fresh_db()
    try:
        _create_legacy_table(conn)
        # Plant a foreign audit_events_migration_new; the
        # repair should refuse rather than clobber it.
        conn.execute("CREATE TABLE audit_events_migration_new (n INTEGER)")
        conn.commit()
        assert repair_audit_events_schema(conn) is False
        # The legacy table must be untouched.
        assert tuple(_legacy_columns(conn)) == AUDIT_EVENT_LEGACY_COLUMNS
    finally:
        conn.close()


def test_repair_preserves_sequence_high_water():
    conn = _fresh_db()
    try:
        _create_legacy_table(conn)
        # Insert enough rows to push the sequence to 5.
        for i in range(3, 6):
            conn.execute(
                "INSERT INTO audit_events (event_id, source_id, source_sequence, "
                "occurred_at, kind, action, status, actor_type, actor_id, agent_id, "
                "run_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"e{i}", f"s{i}", i, 1000 + i, "tool.invoke", "start", "ok",
                 "agent", "main", "main", "r1"),
            )
        conn.commit()
        applied = repair_audit_events_schema(conn)
        assert applied is True
        # Insert a new row and confirm sequence is > 5.
        conn.execute(
            "INSERT INTO audit_events (event_id, source_id, source_sequence, "
            "occurred_at, kind, action, status, actor_type, actor_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("eNew", "sNew", 99, 9999, "tool.invoke", "start", "ok", "agent", "main"),
        )
        conn.commit()
        new_seq = conn.execute(
            "SELECT sequence FROM audit_events WHERE event_id = 'eNew'"
        ).fetchone()[0]
        assert new_seq > 5
    finally:
        conn.close()


def test_repair_creates_indexes():
    conn = _fresh_db()
    try:
        _create_legacy_table(conn)
        repair_audit_events_schema(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = 'audit_events'"
        ).fetchall()
        names = {dict(r)["name"] for r in rows}
        for expected in (
            "idx_audit_events_time",
            "idx_audit_events_agent_sequence",
            "idx_audit_events_session_sequence",
            "idx_audit_events_run_sequence",
            "idx_audit_events_kind_sequence",
            "idx_audit_events_status_sequence",
            "idx_audit_events_channel_sequence",
            "idx_audit_events_direction_sequence",
        ):
            assert expected in names
    finally:
        conn.close()
