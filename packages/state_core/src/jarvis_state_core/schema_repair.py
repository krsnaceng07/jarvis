"""Schema repair + detection for the JARVIS state DB.

Mirrors OpenClaw's
``src/state/openclaw-state-db-schema-repair.ts`` 1:1.
The TS port is the home for:

- ``dropLegacyStateTables`` — drop unreleased transient
  history + retired node pairing tables
- ``repairAgentDatabasesCompositePrimaryKey`` — rebuild
  the ``agent_databases`` table to the canonical
  ``(agent_id, path)`` primary key
- ``markCurrentStateSchemaVersion`` — set
  ``PRAGMA user_version`` + ``schema_meta`` to the
  current canonical version
- ``assertCanonicalStateSchemaShape`` — runtime guard
  that refuses to read a non-canonical state DB
- ``detectJarvisStateDatabaseSchemaMigrations`` — return
  the list of migrations a doctor / startup flow would
  apply to reach the canonical shape

The Python port keeps the same surface and uses the
schema_helpers, audit_migration, operator_approval_migration,
and session_watch_migration modules for the underlying
probes.

Public surface:
- ``drop_legacy_state_tables(conn)``
- ``repair_agent_databases_composite_primary_key(conn)`` -> bool
- ``mark_current_state_schema_version(conn)``
- ``assert_canonical_state_schema_shape(conn, pathname)``
- ``detect_jarvis_state_database_schema_migrations(env, path)``
  -> ``list[StateDatabaseSchemaMigration]``
"""
from __future__ import annotations

import os
import sqlite3
from typing import Optional

from .contract import (
    STATE_SCHEMA_VERSION,
    StateDatabaseSchemaMigration,
)
from .database import StateDatabaseOptions
from .operator_approval_migration import (
    assert_canonical_operator_approval_kinds,
    detect_operator_approval_schema_migration,
)
from .paths import resolve_state_sqlite_path
from .schema_helpers import (
    table_exists,
    table_has_column,
    table_primary_key_columns,
)
from .session_watch_migration import needs_session_watch_cursor_provenance_migration


# State-database connection helpers reused by the
# read-only migration detector. Mirrors the
# ``requireNodeSqlite`` + ``DatabaseSync`` flow in OpenClaw.

_STATE_BUSY_TIMEOUT_MS: int = 5_000


def _open_read_only_db(pathname: str) -> sqlite3.Connection:
    """Open a read-only handle to ``pathname`` for migration detection.

    Mirrors OpenClaw's ``new sqlite.DatabaseSync(pathname,
    { readOnly: true })``. The Python port uses the
    SQLite URI mode so the connection refuses writes
    (URIs: ``file:...?mode=ro``).
    """
    # SQLite URI mode requires a forward-slash path. On
    # Windows we use the canonical path as the URI authority.
    uri = f"file:{pathname}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {int(_STATE_BUSY_TIMEOUT_MS)}")
    return conn


def _read_sqlite_user_version(conn: sqlite3.Connection) -> int:
    """Return the current ``PRAGMA user_version`` for the open connection."""
    row = conn.execute("PRAGMA user_version").fetchone()
    if row is None:
        return 0
    value = row[0]
    if value is None:
        return 0
    return int(value)


def _resolve_database_path(options: StateDatabaseOptions) -> str:
    """Return the absolute state-DB path for ``options``.

    Mirrors ``resolveDatabasePath`` from
    ``openclaw-state-db-maintenance.ts``.
    """
    path = options.get("path")
    if path:
        return os.path.abspath(path)
    return resolve_state_sqlite_path(options.get("env"))


# ── Drop legacy state tables ───────────────────────────────


def drop_legacy_state_tables(conn: sqlite3.Connection) -> None:
    """Drop unreleased transient + retired node-pairing tables.

    Mirrors ``dropLegacyStateTables``. The unreleased
    ``database_verifications`` table was a transient
    history experiment; the retired node pairing tables
    never had a shipped writer. Both are safe to drop
    unconditionally.
    """
    transient_history_table = "_".join(["database", "verifications"])
    conn.executescript(
        f"DROP TABLE IF EXISTS {transient_history_table};\n"
        "DROP TABLE IF EXISTS node_pairing_pending;\n"
        "DROP TABLE IF EXISTS node_pairing_paired;"
    )


# ── agent_databases composite primary key ──────────────────


def has_canonical_agent_databases_primary_key(conn: sqlite3.Connection) -> bool:
    """Return True when ``agent_databases`` PK is the canonical ``(agent_id, path)``.

    Mirrors ``hasCanonicalAgentDatabasesPrimaryKey``. A
    missing ``agent_databases`` table counts as canonical
    (nothing to validate).
    """
    if not table_exists(conn, "agent_databases"):
        return True
    primary_key = table_primary_key_columns(conn, "agent_databases")
    return (
        len(primary_key) == 2
        and primary_key[0] == "agent_id"
        and primary_key[1] == "path"
    )


_AGENT_DATABASES_REQUIRED_COLUMNS = (
    "agent_id",
    "path",
    "schema_version",
    "last_seen_at",
    "size_bytes",
)


def can_repair_agent_databases_primary_key(conn: sqlite3.Connection) -> bool:
    """Return True when the legacy ``agent_databases`` is exactly repairable.

    Mirrors ``canRepairAgentDatabasesPrimaryKey``. The
    check is intentionally strict: matching column names
    alone is not fail-closed (a table with the same names
    but different constraints/defaults/types would get
    its rows copied under a schema that silently discards
    those semantics).
    """
    if not table_exists(conn, "agent_databases"):
        return False
    return all(
        table_has_column(conn, "agent_databases", column)
        for column in _AGENT_DATABASES_REQUIRED_COLUMNS
    )


def repair_agent_databases_composite_primary_key(conn: sqlite3.Connection) -> bool:
    """Rebuild ``agent_databases`` to the canonical ``(agent_id, path)`` PK.

    Mirrors ``repairAgentDatabasesCompositePrimaryKey``.
    Returns ``True`` when the table was rebuilt; ``False``
    when the table is already canonical, missing, or not
    exactly repairable.
    """
    if (
        has_canonical_agent_databases_primary_key(conn)
        or not can_repair_agent_databases_primary_key(conn)
    ):
        return False
    conn.executescript(
        """
        DROP TABLE IF EXISTS agent_databases_migration_new;
        CREATE TABLE agent_databases_migration_new (
          agent_id TEXT NOT NULL,
          path TEXT NOT NULL,
          schema_version INTEGER NOT NULL,
          last_seen_at INTEGER NOT NULL,
          size_bytes INTEGER,
          PRIMARY KEY (agent_id, path)
        );
        INSERT OR REPLACE INTO agent_databases_migration_new (
          agent_id,
          path,
          schema_version,
          last_seen_at,
          size_bytes
        )
        SELECT
          agent_id,
          path,
          schema_version,
          last_seen_at,
          size_bytes
        FROM agent_databases
        WHERE agent_id IS NOT NULL AND path IS NOT NULL;
        DROP TABLE agent_databases;
        ALTER TABLE agent_databases_migration_new RENAME TO agent_databases;
        """
    )
    return True


# ── mark current state schema version ─────────────────────


def mark_current_state_schema_version(conn: sqlite3.Connection) -> None:
    """Set ``PRAGMA user_version`` + ``schema_meta`` to the canonical version.

    Mirrors ``markCurrentStateSchemaVersion``. Pre-v2
    databases can legitimately predate the audit table;
    leave their version untouched so normal open can
    create the complete v2 schema first.
    """
    if not table_exists(conn, "audit_events"):
        return
    conn.execute(f"PRAGMA user_version = {int(STATE_SCHEMA_VERSION)};")
    if (
        table_exists(conn, "schema_meta")
        and all(
            table_has_column(conn, "schema_meta", column)
            for column in ("meta_key", "schema_version", "updated_at")
        )
    ):
        conn.execute(
            "UPDATE schema_meta SET schema_version = ?, updated_at = ? "
            "WHERE meta_key = 'primary'",
            (int(STATE_SCHEMA_VERSION), _now_ms()),
        )


def _now_ms() -> int:
    """Return the current time in milliseconds (Unix epoch)."""
    import time

    return int(time.time() * 1000)


# ── Assert canonical schema shape ──────────────────────────


def assert_canonical_state_schema_shape(
    conn: sqlite3.Connection, pathname: str
) -> None:
    """Raise when the on-disk state DB shape is not canonical.

    Mirrors ``assertCanonicalStateSchemaShape``. The
    runtime guard refuses to read a non-canonical state
    DB; the doctor flow runs the corresponding repair.
    """
    assert_canonical_operator_approval_kinds(conn, pathname)
    if not has_canonical_agent_databases_primary_key(conn):
        raise RuntimeError(
            f"JARVIS state database {pathname} has a legacy agent "
            "database registry schema; run jarvis doctor --fix to "
            "migrate it."
        )
    # Lazy import to avoid the cycle through audit_migration
    # at module load (the audit_migration module is the
    # home of the v2 shape probe).
    from .audit_migration import (
        can_repair_legacy_audit_events_schema,
        has_canonical_audit_events_schema,
    )

    if not has_canonical_audit_events_schema(conn):
        if can_repair_legacy_audit_events_schema(conn):
            raise RuntimeError(
                f"JARVIS state database {pathname} has a legacy audit "
                "event schema; run jarvis doctor --fix to migrate it."
            )
        raise RuntimeError(
            f"JARVIS state database {pathname} has a noncanonical "
            "audit event schema that cannot be repaired automatically; "
            "restore the canonical audit_events shape before retrying."
        )


# ── Detect pending migrations ─────────────────────────────


def detect_jarvis_state_database_schema_migrations(
    options: Optional[StateDatabaseOptions] = None,
) -> list[StateDatabaseSchemaMigration]:
    """Return the list of pending migrations for ``options.path``.

    Mirrors ``detectOpenClawStateDatabaseSchemaMigrations``.
    Opens the state DB read-only, probes the canonical
    shape of every release-known subsystem, and returns
    the migration kinds a doctor / startup flow would
    apply to reach the canonical shape.

    The Python port uses the closed
    ``StateDatabaseSchemaMigration`` TypedDict from
    ``contract.py``; the TS port uses an inline interface.
    """
    from .contract import STATE_STRICT_SCHEMA_VERSION

    options = options or {}
    pathname = _resolve_database_path(options)
    if not os.path.exists(pathname):
        return []
    conn = _open_read_only_db(pathname)
    try:
        migrations: list[StateDatabaseSchemaMigration] = []
        user_version = _read_sqlite_user_version(conn)
        if not has_canonical_agent_databases_primary_key(conn):
            migrations.append(
                {
                    "kind": "agent-databases-composite-primary-key",
                    "path": pathname,
                }
            )
        # Lazy import to avoid the cycle through audit_migration
        # at module load.
        from .audit_migration import has_canonical_audit_events_schema

        if not has_canonical_audit_events_schema(conn):
            migrations.append({"kind": "audit-events-v2", "path": pathname})
        if (
            table_exists(conn, "audit_events")
            and user_version < int(STATE_STRICT_SCHEMA_VERSION)
        ):
            migrations.append(
                {"kind": "strict-tables-v3", "path": pathname}
            )
        if needs_session_watch_cursor_provenance_migration(conn, user_version):
            migrations.append(
                {
                    "kind": "session-watch-cursor-provenance-v4",
                    "path": pathname,
                }
            )
        migrations.extend(detect_operator_approval_schema_migration(conn, pathname))
        return migrations
    finally:
        conn.close()


__all__ = [
    "assert_canonical_state_schema_shape",
    "can_repair_agent_databases_primary_key",
    "detect_jarvis_state_database_schema_migrations",
    "drop_legacy_state_tables",
    "has_canonical_agent_databases_primary_key",
    "mark_current_state_schema_version",
    "repair_agent_databases_composite_primary_key",
]
