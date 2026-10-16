"""Tests for ``jarvis_state_core.schema_repair``.

Covers:
- drop_legacy_state_tables removes the legacy tables
- agent_databases primary-key repair:
  - can_repair returns False when required columns are missing
  - has_canonical returns True on a missing table
  - repair rebuilds the table to the (agent_id, path) PK
  - repair refuses when the shape is not exactly repairable
- mark_current_state_schema_version sets PRAGMA user_version
- assert_canonical_state_schema_shape raises when the
  agent_databases table is not canonical
- detect_jarvis_state_database_schema_migrations returns
  the expected kinds
"""

from __future__ import annotations

import sqlite3

import pytest

from jarvis_state_core.schema_repair import (
    assert_canonical_state_schema_shape,
    can_repair_agent_databases_primary_key,
    detect_jarvis_state_database_schema_migrations,
    drop_legacy_state_tables,
    has_canonical_agent_databases_primary_key,
    mark_current_state_schema_version,
    repair_agent_databases_composite_primary_key,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── drop_legacy_state_tables ───────────────────────────────


def test_drop_legacy_state_tables_drops_unreleased_history():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE database_verifications (id INTEGER)")
        conn.commit()
        drop_legacy_state_tables(conn)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'database_verifications'"
        ).fetchone()
        assert row is None
    finally:
        conn.close()


def test_drop_legacy_state_tables_drops_node_pairing_tables():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE node_pairing_pending (id INTEGER);
            CREATE TABLE node_pairing_paired (id INTEGER);
            """
        )
        conn.commit()
        drop_legacy_state_tables(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE name IN "
            "('node_pairing_pending', 'node_pairing_paired')"
        ).fetchall()
        assert rows == []
    finally:
        conn.close()


def test_drop_legacy_state_tables_is_idempotent():
    conn = _fresh_db()
    try:
        drop_legacy_state_tables(conn)  # no raise
        drop_legacy_state_tables(conn)  # no raise
    finally:
        conn.close()


# ── agent_databases primary-key repair ─────────────────────


def test_has_canonical_returns_true_when_table_missing():
    conn = _fresh_db()
    try:
        assert has_canonical_agent_databases_primary_key(conn) is True
    finally:
        conn.close()


def test_has_canonical_returns_true_for_composite_pk():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT NOT NULL, path TEXT NOT NULL, "
            "PRIMARY KEY (agent_id, path))"
        )
        assert has_canonical_agent_databases_primary_key(conn) is True
    finally:
        conn.close()


def test_has_canonical_returns_false_for_single_column_pk():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE agent_databases (agent_id TEXT NOT NULL PRIMARY KEY, path TEXT)")
        assert has_canonical_agent_databases_primary_key(conn) is False
    finally:
        conn.close()


def test_can_repair_requires_all_required_columns():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE agent_databases (agent_id TEXT, path TEXT)")
        assert can_repair_agent_databases_primary_key(conn) is False
    finally:
        conn.close()


def test_can_repair_returns_true_when_all_columns_present():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT NOT NULL, path TEXT NOT NULL, "
            "schema_version INTEGER NOT NULL, last_seen_at INTEGER NOT NULL, "
            "size_bytes INTEGER, "
            "PRIMARY KEY (agent_id))"
        )
        assert can_repair_agent_databases_primary_key(conn) is True
    finally:
        conn.close()


def test_repair_noop_when_already_canonical():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT NOT NULL, path TEXT NOT NULL, "
            "schema_version INTEGER NOT NULL, last_seen_at INTEGER NOT NULL, "
            "size_bytes INTEGER, "
            "PRIMARY KEY (agent_id, path))"
        )
        assert repair_agent_databases_composite_primary_key(conn) is False
    finally:
        conn.close()


def test_repair_noop_when_shape_not_exactly_repairable():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT NOT NULL, path TEXT NOT NULL, "
            "schema_version INTEGER NOT NULL, last_seen_at INTEGER NOT NULL, "
            "size_bytes INTEGER, "
            "PRIMARY KEY (agent_id, path))"
        )
        conn.execute("INSERT INTO agent_databases VALUES ('a1', 'p1', 1, 1, 100)")
        conn.commit()
        # Already canonical; repair must not destroy data.
        assert repair_agent_databases_composite_primary_key(conn) is False
        row = conn.execute("SELECT COUNT(*) AS c FROM agent_databases").fetchone()
        assert row["c"] == 1
    finally:
        conn.close()


def test_repair_rebuilds_pk_to_canonical():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT NOT NULL, path TEXT NOT NULL, "
            "schema_version INTEGER NOT NULL, last_seen_at INTEGER NOT NULL, "
            "size_bytes INTEGER, "
            "PRIMARY KEY (agent_id))"
        )
        # The whole point of the composite-PK repair is to
        # support multiple paths per agent; insert just one
        # row here (the legacy single-column PK would reject
        # a second row for the same agent) and verify the
        # PK shape changes.
        conn.execute("INSERT INTO agent_databases VALUES ('a1', 'p1', 1, 1, 100)")
        conn.commit()
        assert has_canonical_agent_databases_primary_key(conn) is False
        assert repair_agent_databases_composite_primary_key(conn) is True
        # After rebuild: row is preserved under the
        # (agent_id, path) PK.
        rows = conn.execute("SELECT agent_id, path FROM agent_databases ORDER BY path").fetchall()
        assert [r["path"] for r in rows] == ["p1"]
        # The PK must now be composite.
        assert has_canonical_agent_databases_primary_key(conn) is True
        # And we can now insert a second row for the same
        # agent but a different path.
        conn.execute("INSERT INTO agent_databases VALUES ('a1', 'p2', 1, 2, 200)")
        conn.commit()
        rows = conn.execute("SELECT path FROM agent_databases ORDER BY path").fetchall()
        assert [r["path"] for r in rows] == ["p1", "p2"]
    finally:
        conn.close()


def test_repair_drops_rows_with_null_agent_id_or_path():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT, path TEXT, "
            "schema_version INTEGER, last_seen_at INTEGER, size_bytes INTEGER, "
            "PRIMARY KEY (agent_id))"
        )
        conn.execute("INSERT INTO agent_databases VALUES (NULL, 'p0', 1, 1, 100)")
        conn.execute("INSERT INTO agent_databases VALUES ('a1', 'p1', 1, 1, 100)")
        conn.commit()
        repair_agent_databases_composite_primary_key(conn)
        rows = conn.execute("SELECT path FROM agent_databases").fetchall()
        assert [r["path"] for r in rows] == ["p1"]
    finally:
        conn.close()


# ── mark_current_state_schema_version ──────────────────────


def test_mark_skips_when_audit_events_missing():
    conn = _fresh_db()
    try:
        conn.execute("PRAGMA user_version = 0;")
        mark_current_state_schema_version(conn)
        row = conn.execute("PRAGMA user_version").fetchone()
        # user_version remains 0 because audit_events is missing.
        assert row[0] == 0
    finally:
        conn.close()


def test_mark_sets_user_version_when_audit_events_present():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE audit_events (id INTEGER)")
        conn.commit()
        mark_current_state_schema_version(conn)
        row = conn.execute("PRAGMA user_version").fetchone()
        assert row[0] == int(STATE_SCHEMA_VERSION)
    finally:
        conn.close()


def test_mark_updates_schema_meta_when_present():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE audit_events (id INTEGER);
            CREATE TABLE schema_meta (
              meta_key TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              updated_at INTEGER NOT NULL,
              PRIMARY KEY (meta_key)
            );
            INSERT INTO schema_meta (meta_key, schema_version, updated_at)
              VALUES ('primary', 0, 0);
            """
        )
        conn.commit()
        mark_current_state_schema_version(conn)
        row = conn.execute(
            "SELECT schema_version FROM schema_meta WHERE meta_key = 'primary'"
        ).fetchone()
        assert row["schema_version"] == int(STATE_SCHEMA_VERSION)
    finally:
        conn.close()


# ── assert_canonical_state_schema_shape ────────────────────


def test_assert_passes_on_empty_db():
    conn = _fresh_db()
    try:
        # No tables, no violations.
        assert_canonical_state_schema_shape(conn, "memory:")
    finally:
        conn.close()


def test_assert_raises_on_legacy_agent_databases_pk():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT NOT NULL, path TEXT, "
            "PRIMARY KEY (agent_id))"
        )
        conn.commit()
        with pytest.raises(RuntimeError, match="agent database registry schema"):
            assert_canonical_state_schema_shape(conn, "memory:")
    finally:
        conn.close()


# ── detect_jarvis_state_database_schema_migrations ────────


def test_detect_returns_empty_when_file_missing(tmp_path):
    migrations = detect_jarvis_state_database_schema_migrations(
        {"path": str(tmp_path / "no-such.sqlite")}
    )
    assert migrations == []


def test_detect_finds_legacy_agent_databases_pk(tmp_path):
    db_path = tmp_path / "state.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE agent_databases ("
            "agent_id TEXT NOT NULL, path TEXT, "
            "PRIMARY KEY (agent_id))"
        )
        conn.commit()
    finally:
        conn.close()
    migrations = detect_jarvis_state_database_schema_migrations({"path": str(db_path)})
    kinds = [m["kind"] for m in migrations]
    assert "agent-databases-composite-primary-key" in kinds


def test_detect_finds_legacy_audit_events_shape(tmp_path):
    db_path = tmp_path / "state.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        # Pre-v2 audit_events: shipped before schema_version
        # was added.
        conn.executescript(
            """
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
        )
        conn.commit()
    finally:
        conn.close()
    migrations = detect_jarvis_state_database_schema_migrations({"path": str(db_path)})
    kinds = [m["kind"] for m in migrations]
    assert "audit-events-v2" in kinds


def test_detect_returns_empty_on_canonical_db(tmp_path):
    db_path = tmp_path / "state.sqlite"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.commit()
    finally:
        conn.close()
    migrations = detect_jarvis_state_database_schema_migrations({"path": str(db_path)})
    assert migrations == []
