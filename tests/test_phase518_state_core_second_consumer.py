"""Phase 5.18 — second consumer tests for jarvis_state_core.

These tests prove that the sessions modules
(``session_state_events`` and ``session_upstream_links``)
use ``jarvis_state_core`` as the shared connection
plumbing. The "second consumer" pattern means:
- ``StateDatabase`` owns the connection lifecycle
- Standard pragmas (busy_timeout, WAL, foreign_keys)
  apply to every connection opened via the sessions
  options bag
- ``ensure_schema`` delegates to
  ``jarvis_state_core.ensure_schema`` so the runtime +
  tests share the same baseline
- The per-store-path queue map is reused across calls
  (cache hit)
"""
from __future__ import annotations

import sqlite3

import jarvis_state_core
import pytest

from src.sessions.session_state_events import (
    SessionStateDatabaseOptions,
    _build_state_db,
    _open,
    ensure_schema as events_ensure_schema,
)
from src.sessions.session_upstream_links import (
    SessionUpstreamLinkOptions,
    _build_state_db as upstream_build_state_db,
    _open_connection,
)


# ── Helpers ────────────────────────────────────────────────


def _factory(tmp_path) -> "callable":
    """Build a connection factory backed by a temp file DB."""
    db_path = tmp_path / "state.sqlite"
    db_path.touch()

    def factory() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn

    return factory


# ── StateDatabase ownership ───────────────────────────────


def test_state_events_options_builds_state_db(tmp_path):
    """The sessions options bag produces a ``StateDatabase`` lazily."""
    options = SessionStateDatabaseOptions(connection_factory=_factory(tmp_path))
    state_db = _build_state_db(options)
    assert isinstance(state_db, jarvis_state_core.StateDatabase)
    # Cache hit: second call returns the same instance.
    state_db_2 = _build_state_db(options)
    assert state_db is state_db_2


def test_upstream_link_options_builds_state_db(tmp_path):
    options = SessionUpstreamLinkOptions(connection_factory=_factory(tmp_path))
    state_db = upstream_build_state_db(options)
    assert isinstance(state_db, jarvis_state_core.StateDatabase)
    state_db_2 = upstream_build_state_db(options)
    assert state_db is state_db_2


# ── Standard pragmas ──────────────────────────────────────


def test_state_events_open_applies_standard_pragmas(tmp_path):
    """``_open`` returns a connection with busy_timeout + WAL + FK."""
    options = SessionStateDatabaseOptions(connection_factory=_factory(tmp_path))
    conn = _open(options)
    try:
        # busy_timeout: PRAGMA returns the value in ms.
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy == jarvis_state_core.SQLITE_BUSY_TIMEOUT_MS
        # journal_mode: WAL when the DB file is on disk
        # (in-memory :memory: falls back to MEMORY).
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(journal).lower() == "wal"
        # foreign_keys: ON.
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert int(fk) == 1
    finally:
        conn.close()


def test_upstream_link_open_applies_standard_pragmas(tmp_path):
    options = SessionUpstreamLinkOptions(connection_factory=_factory(tmp_path))
    conn = _open_connection(options)
    try:
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy == jarvis_state_core.SQLITE_BUSY_TIMEOUT_MS
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(journal).lower() == "wal"
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert int(fk) == 1
    finally:
        conn.close()


# ── ensure_schema uses state_core ──────────────────────────


def test_state_events_ensure_schema_creates_canonical_tables(tmp_path):
    """``ensure_schema`` (via state_core) creates the canonical baseline."""
    options = SessionStateDatabaseOptions(connection_factory=_factory(tmp_path))
    events_ensure_schema(options)
    conn = _open(options)
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        # state_core's default baseline.
        assert "session_state_events" in tables
        assert "session_state_heads" in tables
        assert "session_watch_cursors" in tables
        assert "session_upstream_links" in tables
        assert "state_lease_owners" in tables
    finally:
        conn.close()


def test_state_events_ensure_schema_creates_index(tmp_path):
    """The combined DDL includes the per-module index."""
    options = SessionStateDatabaseOptions(connection_factory=_factory(tmp_path))
    events_ensure_schema(options)
    conn = _open(options)
    try:
        idx = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name = 'idx_session_state_events_session'"
        ).fetchone()
        assert idx is not None
    finally:
        conn.close()


# ── Connection-factory is required ─────────────────────────


def test_state_events_open_requires_connection_factory():
    options = SessionStateDatabaseOptions()
    with pytest.raises(ValueError, match="connection_factory is required"):
        _open(options)


def test_upstream_link_open_requires_connection_factory():
    options = SessionUpstreamLinkOptions()
    with pytest.raises(ValueError, match="connection_factory is required"):
        _open_connection(options)


# ── Both modules share the same StateDatabase shape ──────


def test_both_modules_produce_equivalent_state_db(tmp_path):
    """Both sessions modules produce a ``StateDatabase`` with the
    same canonical connection semantics.
    """
    factory = _factory(tmp_path)
    state_db_a = _build_state_db(
        SessionStateDatabaseOptions(connection_factory=factory)
    )
    state_db_b = upstream_build_state_db(
        SessionUpstreamLinkOptions(connection_factory=factory)
    )
    # Both share the per-process queue map (state_core's
    # singleton). The shape is the same even if the
    # StateDatabase instances are different.
    assert isinstance(state_db_a, jarvis_state_core.StateDatabase)
    assert isinstance(state_db_b, jarvis_state_core.StateDatabase)
    assert state_db_a.queues_id() == state_db_b.queues_id()
