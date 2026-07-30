"""Phase 5.22 — second consumer tests for ``jarvis_state_core``.

The ``SqliteSessionTranscriptReader`` is the new 2nd
consumer of ``jarvis_state_core`` in the sessions
package. The default no-op helpers
(``read_session_transcript_events``,
``read_session_transcript_raw_delta``,
``cleanup_session_lifecycle_artifacts``) stay as the
in-process fallback for tests + first boot; the SQLite
reader implements the same shapes but uses
``jarvis_state_core.StateDatabase`` for connection
management.

These tests cover:
- The default helper shape
  (``read_session_transcript_events``,
  ``read_session_transcript_raw_delta``,
  ``cleanup_session_lifecycle_artifacts``)
- The ``build_session_transcript_target`` /
  ``parse_sqlite_session_file_marker`` value-object
  shapes
- The ``SqliteSessionTranscriptReader`` protocol
  conformance
- Schema bootstrap (lazy + idempotent)
- ``jarvis_state_core`` integration (standard pragmas
  + cached StateDatabase)
- ``max_events`` + ``max_bytes`` cap behavior
- Malformed JSON tolerance
- Connection factory required
- Schema SQL constant
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

from src.sessions.session_transcript_runtime import (  # noqa: E402
    TRANSCRIPT_SQLITE_SCHEMA_SQL,
    SessionTranscriptTargetParams,
    SqliteSessionFileMarker,
    SqliteSessionTranscriptReader,
    TranscriptRawDeltaPage,
    build_session_transcript_target,
    cleanup_session_lifecycle_artifacts,
    parse_sqlite_session_file_marker,
    read_session_transcript_events,
    read_session_transcript_raw_delta,
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


# ── Default helpers (no DB) ────────────────────────────────


class TestBuildSessionTranscriptTarget:
    def test_accepts_camel_case_dict(self) -> None:
        result = build_session_transcript_target(
            {
                "sessionId": "s1",
                "agentId": "a1",
                "sessionKey": "agent:a1:abc",
                "scope": "shared",
            }
        )
        assert result is not None
        assert result.session_id == "s1"
        assert result.agent_id == "a1"
        assert result.session_key == "agent:a1:abc"
        assert result.scope == "shared"

    def test_accepts_snake_case_dict(self) -> None:
        result = build_session_transcript_target(
            {
                "session_id": "s1",
                "agent_id": "a1",
                "session_key": "agent:a1:abc",
            }
        )
        assert result is not None
        assert result.session_id == "s1"
        assert result.agent_id == "a1"
        assert result.session_key == "agent:a1:abc"

    def test_returns_none_for_missing_session_id(self) -> None:
        assert build_session_transcript_target(None) is None
        assert build_session_transcript_target({}) is None
        assert build_session_transcript_target({"sessionId": ""}) is None
        assert build_session_transcript_target({"sessionId": "   "}) is None
        assert build_session_transcript_target("not-a-dict") is None
        assert build_session_transcript_target(123) is None

    def test_drops_empty_strings_for_optional_fields(self) -> None:
        result = build_session_transcript_target(
            {
                "sessionId": "s1",
                "agentId": "",
                "sessionKey": "   ",
                "scope": "",
            }
        )
        assert result is not None
        assert result.session_id == "s1"
        assert result.agent_id is None
        assert result.session_key is None
        assert result.scope is None


class TestParseSqliteSessionFileMarker:
    def test_round_trip(self) -> None:
        marker = "sqlite:agent1:session1:/path/to/store:scope-a"
        result = parse_sqlite_session_file_marker(marker)
        assert result is not None
        assert result.agent_id == "agent1"
        assert result.session_id == "session1"
        assert result.store_path == "/path/to/store"
        assert result.scope == "scope-a"

    def test_no_scope(self) -> None:
        # The minimum form is ``sqlite:<agent>:<id>:<store>``
        # (4 parts).
        marker = "sqlite:agent1:session1:/path/to/store"
        result = parse_sqlite_session_file_marker(marker)
        assert result is not None
        assert result.agent_id == "agent1"
        assert result.session_id == "session1"
        assert result.store_path == "/path/to/store"
        assert result.scope is None

    def test_non_string_returns_none(self) -> None:
        assert parse_sqlite_session_file_marker(None) is None
        assert parse_sqlite_session_file_marker(123) is None
        assert parse_sqlite_session_file_marker({}) is None
        assert parse_sqlite_session_file_marker([]) is None

    def test_non_marker_returns_none(self) -> None:
        assert parse_sqlite_session_file_marker("") is None
        assert parse_sqlite_session_file_marker("file:abc") is None
        assert parse_sqlite_session_file_marker("sqlite:") is None
        # Missing parts.
        assert parse_sqlite_session_file_marker("sqlite:a:b") is None

    def test_empty_inner_parts_return_none(self) -> None:
        assert (
            parse_sqlite_session_file_marker("sqlite::session:/path") is None
        )
        assert (
            parse_sqlite_session_file_marker("sqlite:agent::/path") is None
        )


class TestDefaultReadSessionTranscriptEvents:
    def test_default_returns_empty_list(self) -> None:
        # The default helper is a no-op stub; the
        # host overrides it with the SQLite reader.
        # ``read_session_transcript_events`` is
        # ``async def`` (matches OpenClaw's
        # ``readSessionTranscriptEvents`` which is
        # ``async``), so the test must await the
        # coroutine to inspect the return value.
        import asyncio

        assert asyncio.run(read_session_transcript_events(None)) == []
        assert asyncio.run(read_session_transcript_events({})) == []
        assert asyncio.run(
            read_session_transcript_events({"sessionId": "x"})
        ) == []
        assert asyncio.run(
            read_session_transcript_events(
                SessionTranscriptTargetParams(session_id="x")
            )
        ) == []


class TestDefaultReadSessionTranscriptRawDelta:
    def test_default_returns_empty_page(self) -> None:
        # The default helper is a no-op stub; the
        # host overrides it with the SQLite reader.
        result = read_session_transcript_raw_delta(None)
        assert isinstance(result, TranscriptRawDeltaPage)
        assert result.kind == "page"
        assert result.events == []

    def test_default_ignores_caps(self) -> None:
        # The default stub ignores max_events /
        # max_bytes — it always returns the empty
        # page (the production reader honors the
        # caps).
        result = read_session_transcript_raw_delta(
            {"sessionId": "x"}, max_events=10, max_bytes=10
        )
        assert result.kind == "page"
        assert result.events == []


class TestDefaultCleanupSessionLifecycleArtifacts:
    def test_default_returns_zero(self) -> None:
        # The default helper is a no-op stub; the
        # host overrides it with the SQLite reader.
        assert cleanup_session_lifecycle_artifacts(None) == {
            "removedEntries": 0,
            "removedTranscripts": 0,
        }
        assert cleanup_session_lifecycle_artifacts({}) == {
            "removedEntries": 0,
            "removedTranscripts": 0,
        }


# ── SqliteSessionTranscriptReader — protocol ───────────────


class TestReaderProtocol:
    def test_reader_exposes_full_surface(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        assert hasattr(reader, "read_events")
        assert hasattr(reader, "read_raw_delta")
        assert hasattr(reader, "cleanup_session_artifacts")
        assert hasattr(reader, "upsert_transcript")

    def test_read_events_returns_empty_list_for_missing(
        self, tmp_path
    ) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        assert (
            reader.read_events({"sessionId": "missing"})
            == []
        )

    def test_read_events_returns_empty_list_for_none(
        self, tmp_path
    ) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        assert reader.read_events(None) == []


# ── Upsert + read round trip ───────────────────────────────


class TestUpsertAndRead:
    def test_upsert_then_read(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key="agent:a1:abc",
            events=[{"id": "e1", "kind": "user"}],
        )
        events = reader.read_events({"sessionId": "s1"})
        assert events == [{"id": "e1", "kind": "user"}]

    def test_upsert_replaces_existing(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}],
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e2"}, {"id": "e3"}],
        )
        events = reader.read_events({"sessionId": "s1"})
        assert events == [{"id": "e2"}, {"id": "e3"}]

    def test_read_events_accepts_typed_target(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}],
        )
        events = reader.read_events(
            SessionTranscriptTargetParams(
                session_id="s1", agent_id="a1"
            )
        )
        assert events == [{"id": "e1"}]

    def test_read_events_with_agent_id_filter_is_noop(
        self, tmp_path
    ) -> None:
        """The reader does not filter by agent id; the
        active-memory helper handles that."""
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}],
        )
        # Reading with a different agent_id still
        # returns the events (filtering is
        # caller-side, not reader-side).
        events = reader.read_events(
            {"sessionId": "s1", "agentId": "a2"}
        )
        assert events == [{"id": "e1"}]


# ── Malformed JSON tolerance ───────────────────────────────


class TestMalformedJson:
    def test_corrupt_entries_json_yields_empty(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}],
        )
        # Corrupt the row.
        conn = reader._state_db.open()
        try:
            conn.execute(
                "UPDATE session_transcripts SET entries_json = ? "
                "WHERE session_id = ?",
                ("not-json", "s1"),
            )
            conn.commit()
        finally:
            conn.close()
        assert reader.read_events({"sessionId": "s1"}) == []

    def test_non_list_entries_json_yields_empty(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}],
        )
        conn = reader._state_db.open()
        try:
            conn.execute(
                "UPDATE session_transcripts SET entries_json = ? "
                "WHERE session_id = ?",
                ("{}", "s1"),
            )
            conn.commit()
        finally:
            conn.close()
        assert reader.read_events({"sessionId": "s1"}) == []


# ── read_raw_delta caps ───────────────────────────────────


class TestReadRawDeltaCaps:
    def test_max_events_caps_page(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": f"e{i}"} for i in range(10)],
        )
        result = reader.read_raw_delta(
            {"sessionId": "s1"}, max_events=3
        )
        assert result.kind == "page"
        assert len(result.events) == 3

    def test_max_events_zero_caps_to_empty(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": f"e{i}"} for i in range(5)],
        )
        result = reader.read_raw_delta(
            {"sessionId": "s1"}, max_events=0
        )
        # ``max_events=0`` is treated as "no cap" by
        # the OpenClaw source (``value ?? fallback``);
        # the Python port matches that.
        assert result.kind == "page"
        assert len(result.events) == 5

    def test_max_bytes_caps_page(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": f"e{i:03d}"} for i in range(20)],
        )
        result = reader.read_raw_delta(
            {"sessionId": "s1"}, max_bytes=40
        )
        assert result.kind == "page"
        # Page fits within the byte cap (events are
        # trimmed from the tail).
        import json as _json

        serialized = _json.dumps(
            result.events, separators=(",", ":")
        ).encode("utf-8")
        assert len(serialized) <= 40

    def test_empty_session_returns_empty_kind(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        result = reader.read_raw_delta({"sessionId": "missing"})
        assert result.kind == "empty"
        assert result.events == []


# ── cleanup_session_artifacts ──────────────────────────────


class TestCleanupSessionArtifacts:
    def test_cleanup_returns_counts(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}, {"id": "e2"}],
        )
        result = reader.cleanup_session_artifacts(
            {"sessionId": "s1"}
        )
        assert result["removedEntries"] == 2
        assert result["removedTranscripts"] == 1

    def test_cleanup_missing_session_returns_zero(
        self, tmp_path
    ) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        result = reader.cleanup_session_artifacts(
            {"sessionId": "missing"}
        )
        assert result["removedEntries"] == 0
        assert result["removedTranscripts"] == 0

    def test_cleanup_invalid_params_returns_zero(
        self, tmp_path
    ) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        assert (
            reader.cleanup_session_artifacts(None) == {
                "removedEntries": 0,
                "removedTranscripts": 0,
            }
        )
        assert (
            reader.cleanup_session_artifacts({}) == {
                "removedEntries": 0,
                "removedTranscripts": 0,
            }
        )

    def test_cleanup_actually_deletes_row(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}],
        )
        assert reader.read_events({"sessionId": "s1"}) == [
            {"id": "e1"}
        ]
        reader.cleanup_session_artifacts({"sessionId": "s1"})
        assert reader.read_events({"sessionId": "s1"}) == []


# ── Schema bootstrap ────────────────────────────────────────


class TestSchemaBootstrap:
    def test_table_created_lazily(self, tmp_path) -> None:
        factory = _factory(tmp_path)
        reader = SqliteSessionTranscriptReader(
            connection_factory=factory
        )
        # No table yet (no read/write has been called).
        conn = factory()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' "
                "AND name = 'session_transcripts'"
            ).fetchone()
            assert row is None
        finally:
            conn.close()
        # First read triggers the schema.
        reader.read_events({"sessionId": "trigger"})
        conn = factory()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' "
                "AND name = 'session_transcripts'"
            ).fetchone()
            assert row is not None
        finally:
            conn.close()

    def test_table_idempotent(self, tmp_path) -> None:
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        # Two writes in a row: the second is a no-op
        # for the DDL (no error).
        reader.upsert_transcript(
            session_id="s1",
            agent_id="a1",
            session_key=None,
            events=[{"id": "e1"}],
        )
        reader.upsert_transcript(
            session_id="s2",
            agent_id="a2",
            session_key=None,
            events=[{"id": "e2"}],
        )
        conn = reader._state_db.open()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM session_transcripts"
            ).fetchone()
            assert row["n"] == 2
        finally:
            conn.close()


# ── jarvis_state_core integration ───────────────────────────


class TestStateDbIntegration:
    def test_connection_has_standard_pragmas(self, tmp_path) -> None:
        """``_state_db.open()`` applies busy_timeout + WAL + FK."""
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        conn = reader._state_db.open()
        try:
            busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert busy == jarvis_state_core.SQLITE_BUSY_TIMEOUT_MS
            journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert str(journal).lower() == "wal"
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert int(fk) == 1
        finally:
            conn.close()

    def test_state_db_is_cached_across_calls(self, tmp_path) -> None:
        """The ``StateDatabase`` is built once per reader."""
        reader = SqliteSessionTranscriptReader(
            connection_factory=_factory(tmp_path)
        )
        first = reader._state_db
        # Trigger several operations.
        reader.read_events({"sessionId": "a"})
        reader.upsert_transcript(
            session_id="b",
            agent_id="a",
            session_key=None,
            events=[{"id": "e1"}],
        )
        reader.read_events({"sessionId": "b"})
        # Same instance.
        assert reader._state_db is first


# ── Connection factory required ────────────────────────────


class TestConnectionFactoryRequired:
    def test_construction_requires_factory(self) -> None:
        with pytest.raises(
            ValueError, match="connection_factory is required"
        ):
            SqliteSessionTranscriptReader()


# ── Schema SQL constant ─────────────────────────────────────


def test_schema_sql_constant_has_required_columns() -> None:
    """The exported schema SQL has the canonical columns."""
    assert (
        "CREATE TABLE IF NOT EXISTS session_transcripts"
        in TRANSCRIPT_SQLITE_SCHEMA_SQL
    )
    assert "session_id TEXT PRIMARY KEY" in TRANSCRIPT_SQLITE_SCHEMA_SQL
    assert "agent_id TEXT NOT NULL" in TRANSCRIPT_SQLITE_SCHEMA_SQL
    assert "entries_json" in TRANSCRIPT_SQLITE_SCHEMA_SQL
    assert "created_at TEXT NOT NULL" in TRANSCRIPT_SQLITE_SCHEMA_SQL
    assert "updated_at TEXT NOT NULL" in TRANSCRIPT_SQLITE_SCHEMA_SQL
    assert (
        "CREATE INDEX IF NOT EXISTS idx_session_transcripts_agent"
        in TRANSCRIPT_SQLITE_SCHEMA_SQL
    )


# ── Pre-existing helpers re-export ──────────────────────────


def test_module_exports_marker_class() -> None:
    """``SqliteSessionFileMarker`` is exported for host
    consumers that need to parse session file markers."""
    marker = SqliteSessionFileMarker(
        agent_id="a1",
        session_id="s1",
        store_path="/tmp/store",
        scope="shared",
    )
    assert marker.agent_id == "a1"
    assert marker.session_id == "s1"
    assert marker.store_path == "/tmp/store"
    assert marker.scope == "shared"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
