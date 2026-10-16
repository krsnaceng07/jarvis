"""Tests for ``jarvis_state_core.maintenance``.

Covers:
- ``resolve_database_path`` honors env override + custom
  path; falls back to the canonical state DB
- ``create_jarvis_database_verification_error`` returns a
  typed RuntimeError with the right name + message
- ``assert_supported_schema_version`` raises on newer
  user_version; passes on equal + older
- ``assert_jarvis_state_database_for_maintenance`` covers
  every failure mode
- the maintenance schema-compatibility map lists every
  additive column the runtime tolerates alongside the
  canonical shape
"""

from __future__ import annotations

import os
import sqlite3

import pytest

from jarvis_state_core.maintenance import (
    STATE_MAINTENANCE_SCHEMA_COMPATIBILITY,
    assert_jarvis_state_database_for_maintenance,
    assert_supported_schema_version,
    create_jarvis_database_verification_error,
    resolve_database_path,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── resolve_database_path ─────────────────────────────────


def test_resolve_database_path_uses_explicit_path(tmp_path):
    target = tmp_path / "custom.sqlite"
    assert resolve_database_path({"path": str(target)}) == str(target.resolve())


def test_resolve_database_path_falls_back_to_env_state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path / "alt"))
    path = resolve_database_path()
    assert path.endswith(os.path.join("alt", "jarvis.sqlite"))


def test_resolve_database_path_uses_env_dict():
    path = resolve_database_path({"env": {"JARVIS_STATE_DIR": "jarvis-state-x"}})
    assert path.endswith(os.path.join("jarvis-state-x", "jarvis.sqlite"))


# ── create_jarvis_database_verification_error ─────────────


def test_create_verification_error_for_state():
    error = create_jarvis_database_verification_error(
        kind="state", pathname="memory:", stored_error="disk I/O"
    )
    assert isinstance(error, RuntimeError)
    assert error.name == "JarvisSqliteIntegrityError"
    assert "state database memory:" in str(error)
    assert "disk I/O" in str(error)


def test_create_verification_error_for_agent():
    error = create_jarvis_database_verification_error(
        kind="agent", pathname="memory:", stored_error=None
    )
    assert error.name == "JarvisSqliteIntegrityError"
    assert "agent database" in str(error)
    assert "unknown integrity error" in str(error)


# ── assert_supported_schema_version ───────────────────────


def test_assert_supported_passes_on_equal_version():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.execute(f"PRAGMA user_version = {int(STATE_SCHEMA_VERSION)};")
        assert_supported_schema_version(conn, "memory:")  # no raise
    finally:
        conn.close()


def test_assert_supported_passes_on_older_version():
    conn = _fresh_db()
    try:
        conn.execute("PRAGMA user_version = 0;")
        assert_supported_schema_version(conn, "memory:")  # no raise
    finally:
        conn.close()


def test_assert_supported_raises_on_newer_version():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.execute(f"PRAGMA user_version = {int(STATE_SCHEMA_VERSION) + 1};")
        with pytest.raises(RuntimeError, match="schema version"):
            assert_supported_schema_version(conn, "memory:")
    finally:
        conn.close()


# ── assert_jarvis_state_database_for_maintenance ──────────


def test_maintenance_assert_raises_on_newer_user_version():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.execute(f"PRAGMA user_version = {int(STATE_SCHEMA_VERSION) + 1};")
        with pytest.raises(RuntimeError, match="schema version"):
            assert_jarvis_state_database_for_maintenance(conn, {"pathname": "memory:"})
    finally:
        conn.close()


def test_maintenance_assert_raises_on_older_user_version():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.execute(f"PRAGMA user_version = {int(STATE_SCHEMA_VERSION) - 1};")
        with pytest.raises(RuntimeError, match="run jarvis doctor"):
            assert_jarvis_state_database_for_maintenance(conn, {"pathname": "memory:"})
    finally:
        conn.close()


def test_maintenance_assert_raises_on_non_global_role():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.executescript(
            f"""
            PRAGMA user_version = {int(STATE_SCHEMA_VERSION)};
            CREATE TABLE schema_meta (
              meta_key TEXT NOT NULL,
              role TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              PRIMARY KEY (meta_key)
            );
            INSERT INTO schema_meta (meta_key, role, schema_version) VALUES
              ('primary', 'agent', {int(STATE_SCHEMA_VERSION)});
            """
        )
        with pytest.raises(RuntimeError, match="expected global"):
            assert_jarvis_state_database_for_maintenance(conn, {"pathname": "memory:"})
    finally:
        conn.close()


def test_maintenance_assert_raises_on_schema_meta_version_mismatch():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.executescript(
            f"""
            PRAGMA user_version = {int(STATE_SCHEMA_VERSION)};
            CREATE TABLE schema_meta (
              meta_key TEXT NOT NULL,
              role TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              PRIMARY KEY (meta_key)
            );
            INSERT INTO schema_meta (meta_key, role, schema_version) VALUES
              ('primary', 'global', {int(STATE_SCHEMA_VERSION) - 1});
            """
        )
        with pytest.raises(RuntimeError, match="metadata schema version"):
            assert_jarvis_state_database_for_maintenance(conn, {"pathname": "memory:"})
    finally:
        conn.close()


def test_maintenance_assert_passes_on_minimal_canonical_shape():
    """A bare minimum state DB that the runtime would actually
    maintain is accepted. The probe is generous about
    additive columns; it only refuses when the canonical
    tables or the spot-check column are missing.
    """
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.executescript(
            f"""
            PRAGMA user_version = {int(STATE_SCHEMA_VERSION)};
            CREATE TABLE schema_meta (
              meta_key TEXT NOT NULL,
              role TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              PRIMARY KEY (meta_key)
            );
            INSERT INTO schema_meta (meta_key, role, schema_version) VALUES
              ('primary', 'global', {int(STATE_SCHEMA_VERSION)});
            CREATE TABLE session_state_events (sequence INTEGER PRIMARY KEY);
            CREATE TABLE session_state_heads (session_key TEXT PRIMARY KEY);
            CREATE TABLE session_watch_cursors (watcher_session_key TEXT, target_session_key TEXT);
            CREATE TABLE session_upstream_links (session_key TEXT, agent_id TEXT);
            CREATE TABLE state_lease_owners (owner_id TEXT PRIMARY KEY);
            """
        )
        # No commitments table at all: the spot-check skips
        # when the table is missing.
        assert_jarvis_state_database_for_maintenance(conn, {"pathname": "memory:"})  # no raise
    finally:
        conn.close()


def test_maintenance_assert_raises_on_missing_canonical_tables():
    from jarvis_state_core.contract import STATE_SCHEMA_VERSION

    conn = _fresh_db()
    try:
        conn.executescript(
            f"""
            PRAGMA user_version = {int(STATE_SCHEMA_VERSION)};
            CREATE TABLE schema_meta (
              meta_key TEXT NOT NULL,
              role TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              PRIMARY KEY (meta_key)
            );
            INSERT INTO schema_meta (meta_key, role, schema_version) VALUES
              ('primary', 'global', {int(STATE_SCHEMA_VERSION)});
            """
        )
        # Missing every canonical state table.
        with pytest.raises(RuntimeError):
            assert_jarvis_state_database_for_maintenance(conn, {"pathname": "memory:"})
    finally:
        conn.close()


def test_maintenance_assert_raises_on_missing_pathname():
    conn = _fresh_db()
    try:
        with pytest.raises(ValueError, match="pathname required"):
            assert_jarvis_state_database_for_maintenance(conn, {})
    finally:
        conn.close()


# ── STATE_MAINTENANCE_SCHEMA_COMPATIBILITY ────────────────


def test_compatibility_map_lists_all_additive_columns():
    allowed = STATE_MAINTENANCE_SCHEMA_COMPATIBILITY.get("allowed_column_definitions", {})
    expected = {
        "diagnostic_events.sequence",
        "commitments.attempts",
        "commitments.confidence",
        "commitments.created_at_ms",
        "commitments.dedupe_key",
        "commitments.due_timezone",
        "commitments.kind",
        "commitments.reason",
        "commitments.sensitivity",
        "commitments.source",
        "commitments.suggested_text",
        "cron_jobs.created_at_ms",
        "cron_jobs.enabled",
        "cron_jobs.name",
        "cron_jobs.payload_kind",
        "cron_jobs.schedule_kind",
        "cron_jobs.session_target",
        "cron_jobs.wake_mode",
        "current_conversation_bindings.conversation_kind",
        "current_conversation_bindings.target_agent_id",
    }
    assert expected.issubset(allowed.keys())


def test_compatibility_map_values_are_definitions():
    allowed = STATE_MAINTENANCE_SCHEMA_COMPATIBILITY.get("allowed_column_definitions", {})
    # Every value is a non-empty list of column definitions.
    for key, definitions in allowed.items():
        assert isinstance(definitions, list)
        assert len(definitions) >= 1
        for definition in definitions:
            assert isinstance(definition, str)
            assert definition.strip()
