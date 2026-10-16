"""Tests for ``jarvis_state_core.session_watch_migration``.

Covers:
- decode_legacy_ambient_watch_marker_key for valid + invalid
  hex-encoded markers
- has_legacy_ambient_watch_sentinels probes the prefix
- needs_session_watch_cursor_provenance_migration returns
  True for missing column / legacy marker / v<4 user_version
- migrate_session_watch_cursor_provenance:
  - adds the ``provenance`` column when missing
  - promotes matching canonical watch rows
  - drops legacy marker rows
  - no-op when the table is missing
"""

from __future__ import annotations

import sqlite3


from jarvis_state_core.session_watch_migration import (
    LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX,
    SESSION_WATCH_PROVENANCE_AMBIENT_GROUP,
    SESSION_WATCH_PROVENANCE_EXPLICIT,
    SESSION_WATCH_PROVENANCE_SCHEMA_VERSION,
    decode_legacy_ambient_watch_marker_key,
    has_legacy_ambient_watch_sentinels,
    migrate_session_watch_cursor_provenance,
    needs_session_watch_cursor_provenance_migration,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _create_session_watch_cursors(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE session_watch_cursors (
          watcher_session_key TEXT NOT NULL,
          target_session_key TEXT NOT NULL,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY (watcher_session_key, target_session_key)
        )
        """
    )
    conn.commit()


# ── decode_legacy_ambient_watch_marker_key ────────────────


def test_decode_returns_none_for_non_string():
    assert decode_legacy_ambient_watch_marker_key(None) is None  # type: ignore[arg-type]
    assert decode_legacy_ambient_watch_marker_key(123) is None  # type: ignore[arg-type]


def test_decode_returns_none_for_wrong_prefix():
    assert decode_legacy_ambient_watch_marker_key("not-a-marker:abc") is None


def test_decode_returns_none_for_odd_hex_length():
    marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + "abc"
    assert decode_legacy_ambient_watch_marker_key(marker) is None


def test_decode_returns_none_for_non_hex_chars():
    marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + "zzzz"
    assert decode_legacy_ambient_watch_marker_key(marker) is None


def test_decode_returns_decoded_key_for_valid_hex():
    hex_encoded = "6167656e743a6d61696e"  # "agent:main"
    marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + hex_encoded
    assert decode_legacy_ambient_watch_marker_key(marker) == "agent:main"


def test_decode_uppercase_hex():
    hex_encoded = "6167656e743a6d61696e".upper()
    marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + hex_encoded
    assert decode_legacy_ambient_watch_marker_key(marker) == "agent:main"


# ── has_legacy_ambient_watch_sentinels ────────────────────


def test_has_legacy_sentinels_false_when_table_missing():
    conn = _fresh_db()
    try:
        assert has_legacy_ambient_watch_sentinels(conn) is False
    finally:
        conn.close()


def test_has_legacy_sentinels_false_when_table_empty():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        assert has_legacy_ambient_watch_sentinels(conn) is False
    finally:
        conn.close()


def test_has_legacy_sentinels_true_when_marker_present():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + "6167656e743a6d61696e"
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES (?, 'tgt', 1000)",
            (marker,),
        )
        conn.commit()
        assert has_legacy_ambient_watch_sentinels(conn) is True
    finally:
        conn.close()


# ── needs_session_watch_cursor_provenance_migration ───────


def test_needs_migration_false_when_table_missing():
    conn = _fresh_db()
    try:
        assert needs_session_watch_cursor_provenance_migration(conn, 0) is False
    finally:
        conn.close()


def test_needs_migration_true_when_user_version_below_v4():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        assert (
            needs_session_watch_cursor_provenance_migration(
                conn, SESSION_WATCH_PROVENANCE_SCHEMA_VERSION - 1
            )
            is True
        )
    finally:
        conn.close()


def test_needs_migration_true_when_column_missing():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        # user_version = v4, but no provenance column yet.
        assert (
            needs_session_watch_cursor_provenance_migration(
                conn, SESSION_WATCH_PROVENANCE_SCHEMA_VERSION
            )
            is True
        )
    finally:
        conn.close()


def test_needs_migration_false_when_canonical():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        conn.execute(
            "ALTER TABLE session_watch_cursors ADD COLUMN provenance TEXT NOT NULL DEFAULT 'explicit'"
        )
        conn.commit()
        assert (
            needs_session_watch_cursor_provenance_migration(
                conn, SESSION_WATCH_PROVENANCE_SCHEMA_VERSION
            )
            is False
        )
    finally:
        conn.close()


# ── migrate_session_watch_cursor_provenance ───────────────


def test_migrate_noop_when_table_missing():
    conn = _fresh_db()
    try:
        result = migrate_session_watch_cursor_provenance(conn)
        assert result.added_column is False
        assert result.migrated_ambient_watches == 0
        assert result.removed_legacy_sentinels == 0
    finally:
        conn.close()


def test_migrate_adds_column_and_drops_markers_with_no_canonical_pair():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + "6167656e743a6d61696e"
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES (?, 'tgt', 1000)",
            (marker,),
        )
        conn.commit()
        result = migrate_session_watch_cursor_provenance(conn)
        assert result.added_column is True
        # No canonical row existed; the marker is dropped
        # without promoting anything.
        assert result.migrated_ambient_watches == 0
        assert result.removed_legacy_sentinels == 1
        rows = conn.execute("SELECT watcher_session_key FROM session_watch_cursors").fetchall()
        assert rows == []
    finally:
        conn.close()


def test_migrate_promotes_canonical_row_when_pair_exists():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        # Canonical explicit row already present.
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES ('agent:main', 'tgt', 500)"
        )
        # Legacy ambient marker pointing at the same
        # target with a newer updated_at.
        marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + "6167656e743a6d61696e"
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES (?, 'tgt', 1500)",
            (marker,),
        )
        conn.commit()
        result = migrate_session_watch_cursor_provenance(conn)
        assert result.added_column is True
        assert result.migrated_ambient_watches == 1
        assert result.removed_legacy_sentinels == 1
        # After migration: only the canonical row remains,
        # tagged as ambient-group, with the newer timestamp.
        rows = conn.execute(
            "SELECT watcher_session_key, provenance, updated_at FROM session_watch_cursors"
        ).fetchall()
        assert len(rows) == 1
        row = rows[0]
        assert row["watcher_session_key"] == "agent:main"
        assert row["provenance"] == SESSION_WATCH_PROVENANCE_AMBIENT_GROUP
        assert row["updated_at"] == 1500
    finally:
        conn.close()


def test_migrate_promoted_updated_at_is_max_of_both():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        # Canonical row with a newer timestamp than the marker.
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES ('agent:main', 'tgt', 9000)"
        )
        marker = LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX + "6167656e743a6d61696e"
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES (?, 'tgt', 1500)",
            (marker,),
        )
        conn.commit()
        migrate_session_watch_cursor_provenance(conn)
        row = conn.execute(
            "SELECT updated_at FROM session_watch_cursors WHERE watcher_session_key = 'agent:main'"
        ).fetchone()
        # Max of (9000, 1500) == 9000.
        assert row["updated_at"] == 9000
    finally:
        conn.close()


def test_migrate_keeps_explicit_explicit_rows_alone():
    conn = _fresh_db()
    try:
        _create_session_watch_cursors(conn)
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES ('agent:main', 'tgt-a', 1000)"
        )
        conn.execute(
            "INSERT INTO session_watch_cursors "
            "(watcher_session_key, target_session_key, updated_at) "
            "VALUES ('agent:main', 'tgt-b', 2000)"
        )
        conn.commit()
        result = migrate_session_watch_cursor_provenance(conn)
        assert result.added_column is True
        assert result.migrated_ambient_watches == 0
        assert result.removed_legacy_sentinels == 0
        rows = conn.execute(
            "SELECT target_session_key, provenance "
            "FROM session_watch_cursors ORDER BY target_session_key"
        ).fetchall()
        assert len(rows) == 2
        for row in rows:
            assert row["provenance"] == SESSION_WATCH_PROVENANCE_EXPLICIT
    finally:
        conn.close()
