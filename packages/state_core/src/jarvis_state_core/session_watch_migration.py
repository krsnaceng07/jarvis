"""Schema-v4 migration for legacy ambient session-watch sentinel rows.

Mirrors OpenClaw's
``src/state/openclaw-state-db-session-watch-migration.ts``
1:1. The TS port migrates ``session_watch_cursors`` rows
whose ``watcher_session_key`` carries the legacy
``ambient-group-watch:<hex>`` prefix into a structured
``provenance = 'ambient-group'`` column. The Python port
keeps the same surface and uses raw ``sqlite3`` (the TS
port uses Kysely).

Why this is its own migration: the ``provenance`` column
was added in schema v4. Older ambient-group sentinels
encoded the watcher key directly in the
``watcher_session_key`` string so a single column could
serve both the explicit and ambient-group roles; the new
shape stores the same fact in a structured column and
moves the legacy rows into the canonical shape.

Public surface:
- ``SESSION_WATCH_PROVENANCE_SCHEMA_VERSION``
- ``SESSION_WATCH_PROVENANCE_EXPLICIT``
- ``SESSION_WATCH_PROVENANCE_AMBIENT_GROUP``
- ``LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX``
- ``needs_session_watch_cursor_provenance_migration(db, user_version)`` -> ``bool``
- ``SessionWatchCursorProvenanceMigrationResult`` dataclass
- ``migrate_session_watch_cursor_provenance(db)`` ->
  ``SessionWatchCursorProvenanceMigrationResult``
- ``decode_legacy_ambient_watch_marker_key(marker_key)`` -> ``Optional[str]``
"""

from __future__ import annotations

import binascii
import sqlite3
from dataclasses import dataclass
from typing import Optional

from .schema_helpers import ensure_column, table_exists, table_has_column


# Schema version that introduced the ``provenance`` column.
# Mirrors ``SESSION_WATCH_PROVENANCE_SCHEMA_VERSION`` in
# OpenClaw. Note: this is the local sub-version for the
# session_watch_cursors sub-table; the global state DB
# version is in ``contract.STATE_SCHEMA_VERSION``.
SESSION_WATCH_PROVENANCE_SCHEMA_VERSION: int = 4

# Closed set of provenance values stored in the
# ``session_watch_cursors.provenance`` column.
SESSION_WATCH_PROVENANCE_EXPLICIT: str = "explicit"
SESSION_WATCH_PROVENANCE_AMBIENT_GROUP: str = "ambient-group"

# Legacy ambient-group sentinels used this prefix on the
# ``watcher_session_key`` column. The suffix is a hex
# encoding of the real (canonical) ``watcher_session_key``.
LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX: str = "ambient-group-watch:"


def _build_provenance_column_sql() -> str:
    """Return the canonical ``provenance`` column DDL.

    Mirrors ``SESSION_WATCH_PROVENANCE_COLUMN_SQL`` from
    OpenClaw. The Python port builds the SQL inline so the
    constant names stay the single source of truth.
    """
    return (
        f"provenance TEXT NOT NULL DEFAULT "
        f"'{SESSION_WATCH_PROVENANCE_EXPLICIT}' "
        f"CHECK (provenance IN ("
        f"'{SESSION_WATCH_PROVENANCE_EXPLICIT}', "
        f"'{SESSION_WATCH_PROVENANCE_AMBIENT_GROUP}'))"
    )


# ── Schema probes ──────────────────────────────────────────


def has_legacy_ambient_watch_sentinels(conn: sqlite3.Connection) -> bool:
    """Return True when any sentinel row still uses the legacy prefix.

    Mirrors ``hasLegacyAmbientWatchSentinels``.
    """
    if not table_exists(conn, "session_watch_cursors"):
        return False
    row = conn.execute(
        "SELECT 1 FROM session_watch_cursors WHERE watcher_session_key LIKE ? LIMIT 1",
        (f"{LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX}%",),
    ).fetchone()
    return row is not None


def needs_session_watch_cursor_provenance_migration(
    conn: sqlite3.Connection, user_version: int
) -> bool:
    """Return True when ``session_watch_cursors`` needs the v4 migration.

    Mirrors ``needsSessionWatchCursorProvenanceMigration``.
    Triggers when:
    - the user_version is below v4
    - the ``provenance`` column is missing
    - any legacy ambient-group sentinel rows still exist
    """
    if not table_exists(conn, "session_watch_cursors"):
        return False
    return (
        user_version < SESSION_WATCH_PROVENANCE_SCHEMA_VERSION
        or not table_has_column(conn, "session_watch_cursors", "provenance")
        or has_legacy_ambient_watch_sentinels(conn)
    )


# ── Decoding ───────────────────────────────────────────────


def decode_legacy_ambient_watch_marker_key(marker_key: str) -> Optional[str]:
    """Decode a legacy ambient-group marker into the real watcher key.

    Mirrors ``decodeLegacyAmbientWatchMarkerKey``. Returns
    ``None`` when the marker is not a valid hex-encoded
    string; the migration treats ``None`` as "drop the
    sentinel" because the original watcher key is
    irrecoverable.
    """
    if not isinstance(marker_key, str) or not marker_key.startswith(
        LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX
    ):
        return None
    encoded = marker_key[len(LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX) :]
    if not encoded or len(encoded) % 2 != 0:
        return None
    if not all(c in "0123456789abcdefABCDEF" for c in encoded):
        return None
    try:
        return bytes.fromhex(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None


# ── Migration ──────────────────────────────────────────────


@dataclass
class SessionWatchCursorProvenanceMigrationResult:
    """Summary of a ``migrate_session_watch_cursor_provenance`` call.

    Mirrors the OpenClaw return type
    ``SessionWatchCursorProvenanceMigrationResult``.
    """

    added_column: bool
    migrated_ambient_watches: int
    removed_legacy_sentinels: int


def _read_legacy_marker_rows(
    conn: sqlite3.Connection,
) -> list[tuple[str, str, int]]:
    """Read all legacy ambient-group marker rows.

    Returns ``(watcher_session_key, target_session_key, updated_at)`` tuples.
    """
    cursor = conn.execute(
        "SELECT watcher_session_key, target_session_key, updated_at "
        "FROM session_watch_cursors "
        "WHERE watcher_session_key LIKE ?",
        (f"{LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX}%",),
    )
    return [(str(r[0]), str(r[1]), int(r[2])) for r in cursor.fetchall()]


def _read_watch(
    conn: sqlite3.Connection, watcher_session_key: str, target_session_key: str
) -> Optional[int]:
    """Read the ``updated_at`` for an existing canonical watch row."""
    row = conn.execute(
        "SELECT updated_at FROM session_watch_cursors "
        "WHERE watcher_session_key = ? AND target_session_key = ?",
        (watcher_session_key, target_session_key),
    ).fetchone()
    return None if row is None else int(row[0])


def _promote_watch(
    conn: sqlite3.Connection,
    *,
    watcher_session_key: str,
    target_session_key: str,
    provenance: str,
    updated_at: int,
) -> int:
    """Promote a canonical watch row to ``ambient-group`` provenance.

    Returns the number of affected rows.
    """
    cursor = conn.execute(
        "UPDATE session_watch_cursors "
        "SET provenance = ?, updated_at = ? "
        "WHERE watcher_session_key = ? AND target_session_key = ?",
        (provenance, updated_at, watcher_session_key, target_session_key),
    )
    return cursor.rowcount or 0


def _delete_legacy_marker(
    conn: sqlite3.Connection,
    *,
    watcher_session_key: str,
    target_session_key: str,
) -> int:
    """Delete a legacy marker row.

    Returns the number of affected rows.
    """
    cursor = conn.execute(
        "DELETE FROM session_watch_cursors "
        "WHERE watcher_session_key = ? AND target_session_key = ?",
        (watcher_session_key, target_session_key),
    )
    return cursor.rowcount or 0


def migrate_session_watch_cursor_provenance(
    conn: sqlite3.Connection,
) -> SessionWatchCursorProvenanceMigrationResult:
    """Migrate legacy ambient-group sentinels into the v4 shape.

    Mirrors ``migrateSessionWatchCursorProvenance``. The
    caller owns the surrounding ``BEGIN IMMEDIATE``
    transaction so the column add, paired
    read+promote+delete triplet, and unique-index rebuild
    roll back together on any error.

    The Python port's read+promote+delete triplet preserves
    the OpenClaw "pair the timestamp read and update
    together" semantic without Kysely: each marker is
    read, the canonical row is read inside the same
    transaction, the promotion writes
    ``max(watch.updated_at, marker.updated_at)``, then the
    marker is deleted.
    """
    if not table_exists(conn, "session_watch_cursors"):
        return SessionWatchCursorProvenanceMigrationResult(
            added_column=False,
            migrated_ambient_watches=0,
            removed_legacy_sentinels=0,
        )
    added_column = ensure_column(conn, "session_watch_cursors", _build_provenance_column_sql())
    legacy_markers = _read_legacy_marker_rows(conn)
    migrated = 0
    for watcher_session_key, target_session_key, marker_updated_at in legacy_markers:
        decoded_watcher_key = decode_legacy_ambient_watch_marker_key(watcher_session_key)
        if decoded_watcher_key is not None:
            watch_updated_at = _read_watch(conn, decoded_watcher_key, target_session_key)
            if watch_updated_at is not None:
                promoted = _promote_watch(
                    conn,
                    watcher_session_key=decoded_watcher_key,
                    target_session_key=target_session_key,
                    provenance=SESSION_WATCH_PROVENANCE_AMBIENT_GROUP,
                    updated_at=max(watch_updated_at, marker_updated_at),
                )
                migrated += promoted
        # Drop the legacy sentinel regardless of whether
        # the canonical row existed (mirrors the OpenClaw
        # flow: the marker is a duplicate).
        _delete_legacy_marker(
            conn,
            watcher_session_key=watcher_session_key,
            target_session_key=target_session_key,
        )
    return SessionWatchCursorProvenanceMigrationResult(
        added_column=added_column,
        migrated_ambient_watches=migrated,
        removed_legacy_sentinels=len(legacy_markers),
    )


__all__ = [
    "LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX",
    "SESSION_WATCH_PROVENANCE_AMBIENT_GROUP",
    "SESSION_WATCH_PROVENANCE_EXPLICIT",
    "SESSION_WATCH_PROVENANCE_SCHEMA_VERSION",
    "SessionWatchCursorProvenanceMigrationResult",
    "decode_legacy_ambient_watch_marker_key",
    "has_legacy_ambient_watch_sentinels",
    "migrate_session_watch_cursor_provenance",
    "needs_session_watch_cursor_provenance_migration",
]
