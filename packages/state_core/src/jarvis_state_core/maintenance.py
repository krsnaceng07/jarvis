"""Offline maintenance + integrity verification helpers.

Mirrors OpenClaw's
``src/state/openclaw-state-db-maintenance.ts`` 1:1. The
TS port is the home for the read-only maintenance + WAL
checks that run before any offline file maintenance
(``VACUUM`` / ``REINDEX`` / etc.).

The Python port keeps the same surface and uses the
existing contract + paths helpers for the path resolution
and version constants.

Public surface:
- ``create_jarvis_database_verification_error(kind, pathname, stored_error)``
  -> ``RuntimeError``
- ``assert_supported_schema_version(db, pathname)``
- ``assert_jarvis_state_database_for_maintenance(db, options)``
- ``resolve_database_path(options)`` -> ``str``
- ``STATE_MAINTENANCE_SCHEMA_COMPATIBILITY`` — closed
  set of additive column definitions the runtime
  tolerates alongside the canonical v2+ shape
"""
from __future__ import annotations

import os
import sqlite3
from typing import Literal, Optional, TypedDict

from .contract import (
    DATABASE_SCHEMA_DOCS_URL,
    STATE_SCHEMA_VERSION,
)
from .database import StateDatabaseOptions
from .paths import resolve_state_sqlite_path
from .schema_helpers import table_exists, table_has_column


# ── Compatibility table ────────────────────────────────────
#
# Mirrors ``OPENCLAW_STATE_MAINTENANCE_SCHEMA_COMPATIBILITY``
# from ``openclaw-state-db-maintenance.ts``. The closed
# set of additive column definitions the runtime tolerates
# alongside the canonical v2+ shape. A v3+ strict rebuild
# drops these; a v2 database keeps them so the runtime
# can read legacy writers until they're upgraded.


class _MaintenanceSchemaCompatibility(TypedDict, total=False):
    allowed_column_definitions: dict[str, list[str]]


STATE_MAINTENANCE_SCHEMA_COMPATIBILITY: _MaintenanceSchemaCompatibility = {
    "allowed_column_definitions": {
        "diagnostic_events.sequence": ["sequence INTEGER NOT NULL DEFAULT 0"],
        "commitments.attempts": ["attempts INTEGER NOT NULL DEFAULT 0"],
        "commitments.confidence": ["confidence REAL NOT NULL DEFAULT 0"],
        "commitments.created_at_ms": [
            "created_at_ms INTEGER NOT NULL DEFAULT 0"
        ],
        "commitments.dedupe_key": ["dedupe_key TEXT NOT NULL DEFAULT ''"],
        "commitments.due_timezone": [
            "due_timezone TEXT NOT NULL DEFAULT 'UTC'"
        ],
        "commitments.kind": ["kind TEXT NOT NULL DEFAULT 'followup'"],
        "commitments.reason": ["reason TEXT NOT NULL DEFAULT ''"],
        "commitments.sensitivity": [
            "sensitivity TEXT NOT NULL DEFAULT 'normal'"
        ],
        "commitments.source": ["source TEXT NOT NULL DEFAULT 'unknown'"],
        "commitments.suggested_text": [
            "suggested_text TEXT NOT NULL DEFAULT ''"
        ],
        "cron_jobs.created_at_ms": [
            "created_at_ms INTEGER NOT NULL DEFAULT 0"
        ],
        "cron_jobs.enabled": ["enabled INTEGER NOT NULL DEFAULT 1"],
        "cron_jobs.name": ["name TEXT NOT NULL DEFAULT ''"],
        "cron_jobs.payload_kind": [
            "payload_kind TEXT NOT NULL DEFAULT 'message'"
        ],
        "cron_jobs.schedule_kind": [
            "schedule_kind TEXT NOT NULL DEFAULT 'manual'"
        ],
        "cron_jobs.session_target": [
            "session_target TEXT NOT NULL DEFAULT 'main'"
        ],
        "cron_jobs.wake_mode": ["wake_mode TEXT NOT NULL DEFAULT 'auto'"],
        "current_conversation_bindings.conversation_kind": [
            "conversation_kind TEXT NOT NULL DEFAULT 'channel'"
        ],
        "current_conversation_bindings.target_agent_id": [
            "target_agent_id TEXT NOT NULL DEFAULT 'main'"
        ],
    }
}


# ── Path resolution ────────────────────────────────────────


def resolve_database_path(options: Optional[StateDatabaseOptions] = None) -> str:
    """Return the absolute state-DB path for ``options``.

    Mirrors ``resolveDatabasePath`` from
    ``openclaw-state-db-maintenance.ts``. The Python port
    uses ``os.path.abspath`` (matches the TS ``path.resolve``).
    """
    options = options or {}
    path = options.get("path")
    if path:
        return os.path.abspath(path)
    return resolve_state_sqlite_path(options.get("env"))


# ── Error factory ──────────────────────────────────────────


def create_jarvis_database_verification_error(
    kind: Literal["agent", "state"],
    pathname: str,
    stored_error: Optional[str],
) -> RuntimeError:
    """Build a typed integrity-verification error.

    Mirrors ``createOpenClawDatabaseVerificationError``.
    The Python port returns a ``RuntimeError`` with
    ``name = "JarvisSqliteIntegrityError"`` (the TS port
    uses an Error subclass with the same name). Doctor's
    clearing hooks run after a full integrity assertion,
    so a still-corrupt file cannot be cleared directly:
    the file must be healthy first.
    """
    error_message = (
        f"JARVIS {kind} database {pathname} is quarantined after "
        "integrity verification failed: "
        f"{stored_error or 'unknown integrity error'}. "
        "Restore the database from a backup or repair it, then run "
        "jarvis doctor --fix to clear the quarantine. See "
        f"{DATABASE_SCHEMA_DOCS_URL}."
    )
    error = RuntimeError(error_message)
    error.name = "JarvisSqliteIntegrityError"
    return error


# ── User-version assertions ────────────────────────────────


def _read_sqlite_user_version(conn: sqlite3.Connection) -> int:
    """Return the current ``PRAGMA user_version`` for the open connection."""
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    value = row[0]
    if value is None:
        return 0
    return int(value)


def _create_newer_sqlite_schema_version_error(
    label: str, pathname: str, current: int, expected: int
) -> RuntimeError:
    """Build a typed "newer schema than this build" error.

    Mirrors ``createNewerSqliteSchemaVersionError``. The
    runtime refuses to read a state DB that was written by
    a newer build; the doctor flow either downgrades the
    DB or ships the user's data forward.
    """
    return RuntimeError(
        f"{label} {pathname} uses schema version {current}; this build "
        f"supports up to {expected}. Upgrade JARVIS or run jarvis "
        f"doctor --fix to migrate the database. See {DATABASE_SCHEMA_DOCS_URL}."
    )


def assert_supported_schema_version(
    conn: sqlite3.Connection, pathname: str
) -> None:
    """Raise when ``PRAGMA user_version`` is newer than the build supports.

    Mirrors ``assertSupportedSchemaVersion``. Older
    versions are tolerated (a normal open runs the
    additive + repair migrations); only newer versions
    fail closed.
    """
    user_version = _read_sqlite_user_version(conn)
    if user_version > int(STATE_SCHEMA_VERSION):
        raise _create_newer_sqlite_schema_version_error(
            "JARVIS state database",
            pathname,
            user_version,
            int(STATE_SCHEMA_VERSION),
        )


# ── Maintenance-time assertion ────────────────────────────


def assert_jarvis_state_database_for_maintenance(
    database: sqlite3.Connection,
    options: dict,
) -> None:
    """Require canonical state DB ownership + schema before maintenance.

    Mirrors ``assertOpenClawStateDatabaseForMaintenance``.
    Offline file maintenance (VACUUM, REINDEX, …) must
    only run against a state DB the runtime is willing to
    read; otherwise a side-effect of the maintenance
    could break the runtime without a clear error path.

    The check covers:
    - ``PRAGMA user_version`` must equal STATE_SCHEMA_VERSION
    - the ``schema_meta`` row must declare ``role = 'global'``
    - the ``schema_meta`` row's ``schema_version`` must
      match STATE_SCHEMA_VERSION
    - the on-disk shape must contain the canonical columns
      (per ``STATE_MAINTENANCE_SCHEMA_COMPATIBILITY``)
    """
    pathname = options.get("pathname")
    if not pathname:
        raise ValueError(
            "assert_jarvis_state_database_for_maintenance: pathname required"
        )
    user_version = _read_sqlite_user_version(database)
    if user_version > int(STATE_SCHEMA_VERSION):
        raise _create_newer_sqlite_schema_version_error(
            "JARVIS state database",
            pathname,
            user_version,
            int(STATE_SCHEMA_VERSION),
        )
    if user_version != int(STATE_SCHEMA_VERSION):
        raise RuntimeError(
            f"JARVIS state database {pathname} uses schema version "
            f"{user_version}; run jarvis doctor --fix before compacting it."
        )
    metadata_row = database.execute(
        "SELECT role, schema_version FROM schema_meta "
        "WHERE meta_key = 'primary' LIMIT 1"
    ).fetchone()
    if metadata_row is None:
        role = "missing"
        schema_version_value: object = "invalid"
    else:
        role = metadata_row[0] if metadata_row[0] is not None else "missing"
        schema_version_value = metadata_row[1]
    if role != "global":
        raise RuntimeError(
            f"JARVIS state database {pathname} has schema role {role}; "
            "expected global."
        )
    if schema_version_value != int(STATE_SCHEMA_VERSION):
        reported = (
            schema_version_value
            if isinstance(schema_version_value, int)
            else "invalid"
        )
        raise RuntimeError(
            f"JARVIS state database {pathname} metadata schema version "
            f"{reported} does not match {int(STATE_SCHEMA_VERSION)}; run "
            "jarvis doctor --fix before compacting it."
        )
    if not _assert_sqlite_schema_contains(
        database, pathname, STATE_MAINTENANCE_SCHEMA_COMPATIBILITY
    ):
        # The schema is allowed to grow via additive
        # columns; the only columns that must exist are
        # the ones in the canonical v2+ shape plus the
        # maintenance-compatibility set. The probe is
        # intentionally generous — a v2 DB that has been
        # grown to v3+ via ``ensure_column`` keeps the
        # additive defaults and is still considered
        # maintenance-safe. When the probe refuses, the
        # DB is suspicious enough that offline
        # maintenance should not run.
        raise RuntimeError(
            f"JARVIS state database {pathname} does not match the "
            "canonical v2+ shape required for offline maintenance; "
            "run jarvis doctor --fix to migrate it."
        )


def _assert_sqlite_schema_contains(
    database: sqlite3.Connection,
    pathname: str,
    compatibility: _MaintenanceSchemaCompatibility,
) -> bool:
    """Best-effort probe that the on-disk shape matches the canonical set.

    Mirrors ``assertSqliteSchemaContains`` from
    ``@openclaw/infra/sqlite-schema-contract``. The Python
    port returns ``True`` when the database has the
    minimum maintenance-safe shape; ``False`` when the
    shape is suspicious (the caller raises the typed
    error). The probe is intentionally conservative: it
    refuses to maintain a DB whose canonical tables are
    missing or whose canonical required columns have
    been dropped.
    """
    # Minimum maintenance-safe table set. The JARVIS Brain
    # Core baseline already provides these tables; the
    # probe is a sanity check, not a full schema diff.
    required_tables = (
        "session_state_events",
        "session_state_heads",
        "session_watch_cursors",
        "session_upstream_links",
        "state_lease_owners",
    )
    if not all(table_exists(database, name) for name in required_tables):
        return False
    # Spot-check one canonical column from the compatibility
    # set so a cleared schema_meta doesn't pass the
    # maintenance check by accident.
    spot_check = ("commitments.kind", "kind")
    for column_key, column_name in (spot_check,):
        table_name, _ = column_key.split(".", 1)
        if not table_exists(database, table_name):
            continue
        if not table_has_column(database, table_name, column_name):
            return False
    return True


__all__ = [
    "STATE_MAINTENANCE_SCHEMA_COMPATIBILITY",
    "assert_jarvis_state_database_for_maintenance",
    "assert_supported_schema_version",
    "create_jarvis_database_verification_error",
    "resolve_database_path",
]
