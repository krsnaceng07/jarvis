"""Audit-event schema migration.

Mirrors OpenClaw's ``src/state/openclaw-state-db-audit-migration.ts``.
The TS port migrates a single legacy ``audit_events`` table
shape (no ``schema_version`` column) into the v2 shape with
versioned message-lifecycle columns. The Python port is
identical but operates on a generic ``sqlite3.Connection``.

The migration is intentionally conservative: it only runs
when the on-disk shape is the exact legacy shape AND the
surrounding repair transaction can roll the table swap
back atomically. Foreign ``audit_events_migration_new``
tables fail closed (the new table is foreign data, not
the migration's own scratch space).

Public surface:
- ``AUDIT_EVENT_STATE_SCHEMA_VERSION``
- ``AUDIT_EVENT_LEGACY_COLUMNS``
- ``AUDIT_EVENT_V2_COLUMNS``
- ``has_canonical_audit_events_schema(conn)``
- ``can_repair_legacy_audit_events_schema(conn)``
- ``repair_audit_events_schema(conn)``
"""
from __future__ import annotations

import sqlite3
from typing import Optional


# The v2 audit-event ledger adds ``schema_version`` + a
# block of message-lifecycle columns (direction, channel,
# conversation_kind, message_outcome, reason_code,
# delivery_kind, failure_stage, duration_ms, result_count,
# account_ref, conversation_ref, message_ref, target_ref).
AUDIT_EVENT_STATE_SCHEMA_VERSION: int = 2

# The legacy shape: shipped in v0.5, retired in v0.6.
AUDIT_EVENT_LEGACY_COLUMNS = (
    "sequence",
    "event_id",
    "source_id",
    "source_sequence",
    "occurred_at",
    "kind",
    "action",
    "status",
    "error_code",
    "actor_type",
    "actor_id",
    "agent_id",
    "session_key",
    "session_id",
    "run_id",
    "tool_call_id",
    "tool_name",
)

# The v2 shape: adds ``schema_version`` + message-lifecycle
# columns. Must be applied as a transactional table swap
# so partial migration never reaches runtime.
AUDIT_EVENT_V2_COLUMNS = (
    "sequence",
    "event_id",
    "source_id",
    "schema_version",
    "source_sequence",
    "occurred_at",
    "kind",
    "action",
    "status",
    "error_code",
    "actor_type",
    "actor_id",
    "agent_id",
    "session_key",
    "session_id",
    "run_id",
    "tool_call_id",
    "tool_name",
    "direction",
    "channel",
    "conversation_kind",
    "message_outcome",
    "reason_code",
    "delivery_kind",
    "failure_stage",
    "duration_ms",
    "result_count",
    "account_ref",
    "conversation_ref",
    "message_ref",
    "target_ref",
)

# Mirrors ``AUDIT_EVENT_V2_REQUIRED_NOT_NULL_COLUMNS`` from
# OpenClaw (the v2 schema requires every column to be NOT
# NULL; the migration rebuilds the table to honor that).
AUDIT_EVENT_V2_REQUIRED_NOT_NULL_COLUMNS = (
    "event_id",
    "source_id",
    "schema_version",
    "source_sequence",
    "occurred_at",
    "kind",
    "action",
    "status",
    "actor_type",
    "actor_id",
)

# Legacy required NOT NULL columns (smaller set). The
# legacy table did NOT mark ``agent_id`` / ``run_id`` as
# NOT NULL (both were nullable); only the v2 shape marks
# them NOT NULL.
AUDIT_EVENT_LEGACY_REQUIRED_NOT_NULL_COLUMNS = (
    "event_id",
    "source_id",
    "source_sequence",
    "occurred_at",
    "kind",
    "action",
    "status",
    "actor_type",
    "actor_id",
)


# ── Schema probes ────────────────────────────────────────


def _table_column_info(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    """Return the ``PRAGMA table_info`` rows for a table as plain dicts."""
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [
        {
            "name": row[1],
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5],
        }
        for row in rows
    ]


def _table_sql(conn: sqlite3.Connection, table_name: str) -> Optional[str]:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return str(row[0])


def _table_has_column(
    conn: sqlite3.Connection, table_name: str, column_name: str
) -> bool:
    return any(
        column.get("name") == column_name
        for column in _table_column_info(conn, table_name)
    )


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 AS ok FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row and row[0] == 1)


def _table_primary_key_columns(
    conn: sqlite3.Connection, table_name: str
) -> list[str]:
    return [
        column["name"]
        for column in sorted(
            _table_column_info(conn, table_name),
            key=lambda c: int(c.get("pk") or 0),
        )
        if int(column.get("pk") or 0) > 0
        and isinstance(column.get("name"), str)
    ]


def _table_has_exact_columns(
    conn: sqlite3.Connection, table_name: str, expected: tuple
) -> bool:
    names = [
        column.get("name")
        for column in _table_column_info(conn, table_name)
    ]
    return len(names) == len(expected) and all(
        names[i] == expected[i] for i in range(len(expected))
    )


def _table_has_required_columns(
    conn: sqlite3.Connection, table_name: str, required: tuple
) -> bool:
    columns = {
        column.get("name"): column
        for column in _table_column_info(conn, table_name)
    }
    return all(
        int(columns.get(name, {}).get("notnull") or 0) == 1
        for name in required
    )


def _table_has_unique_column(
    conn: sqlite3.Connection, table_name: str, column_name: str
) -> bool:
    indexes = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    for index in indexes:
        # ``PRAGMA index_list`` columns:
        # seq, name, unique, origin, partial
        if int(index[2] or 0) != 1:
            continue
        name = index[1]
        if not isinstance(name, str):
            continue
        # PRAGMA index_info uses a quoted identifier.
        escaped = name.replace("'", "''")
        columns = conn.execute(
            f"PRAGMA index_info('{escaped}')"
        ).fetchall()
        # ``PRAGMA index_info`` columns: seqno, cid, name
        column_names = [col[2] for col in columns]
        if len(column_names) == 1 and column_names[0] == column_name:
            return True
    return False


# ── Canonical-shape checks ────────────────────────────────


def _has_canonical_audit_event_table(
    conn: sqlite3.Connection,
    expected_columns: tuple,
    required_columns: tuple,
) -> bool:
    sql = (_table_sql(conn, "audit_events") or "").lower()
    return (
        _table_has_exact_columns(conn, "audit_events", expected_columns)
        and _table_primary_key_columns(conn, "audit_events") == ["sequence"]
        and _table_has_required_columns(conn, "audit_events", required_columns)
        and bool(sql)
        and "sequence integer primary key autoincrement" in sql
        and _table_has_unique_column(conn, "audit_events", "event_id")
        and _table_has_unique_column(conn, "audit_events", "source_id")
    )


def _has_canonical_audit_identity_key_table(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, "audit_identity_keys"):
        return False
    sql = (_table_sql(conn, "audit_identity_keys") or "").lower()
    return (
        _table_has_exact_columns(
            conn, "audit_identity_keys", ("id", "key_id", "key", "created_at")
        )
        and _table_primary_key_columns(conn, "audit_identity_keys") == ["id"]
        and _table_has_required_columns(
            conn, "audit_identity_keys", ("id", "key_id", "key", "created_at")
        )
        and bool(sql)
        and "check (id = 1)" in sql
    )


def has_canonical_audit_events_schema(conn: sqlite3.Connection) -> bool:
    """Return True when ``audit_events`` matches the v2 shape.

    Mirrors ``hasCanonicalAuditEventsSchema``. When the
    table is missing entirely we treat the DB as
    pre-migration (return True only if the user_version
    indicates we haven't reached v2 yet AND the identity
    table is also missing).
    """
    if not _table_exists(conn, "audit_events"):
        user_version_row = conn.execute("PRAGMA user_version").fetchone()
        user_version = int((user_version_row or (0,))[0] or 0)
        return (
            user_version < AUDIT_EVENT_STATE_SCHEMA_VERSION
            and not _table_exists(conn, "audit_identity_keys")
        )
    return _has_canonical_audit_event_table(
        conn, AUDIT_EVENT_V2_COLUMNS, AUDIT_EVENT_V2_REQUIRED_NOT_NULL_COLUMNS
    ) and _has_canonical_audit_identity_key_table(conn)


def can_repair_legacy_audit_events_schema(conn: sqlite3.Connection) -> bool:
    """Return True when the legacy shape is exactly the shipped one.

    Mirrors ``canRepairLegacyAuditEventsSchema``. Refuses
    if a foreign ``audit_events_migration_new`` table
    exists (could be unrelated data) or if the legacy
    table already has ``schema_version`` (already a v2
    table by another name).
    """
    if (
        not _table_exists(conn, "audit_events")
        or _table_exists(conn, "audit_events_migration_new")
        or _table_has_column(conn, "audit_events", "schema_version")
    ):
        return False
    identity_safe = not _table_exists(
        conn, "audit_identity_keys"
    ) or _has_canonical_audit_identity_key_table(conn)
    return identity_safe and _has_canonical_audit_event_table(
        conn, AUDIT_EVENT_LEGACY_COLUMNS, AUDIT_EVENT_LEGACY_REQUIRED_NOT_NULL_COLUMNS
    )


# ── Sequence high-water-mark helpers ──────────────────────


def _read_audit_event_sequence_high_water(
    conn: sqlite3.Connection,
) -> Optional[int]:
    if not _table_exists(conn, "sqlite_sequence"):
        return None
    row = conn.execute(
        "SELECT CAST(seq AS TEXT) AS seq FROM sqlite_sequence WHERE name = 'audit_events'"
    ).fetchone()
    if row is None or row[0] is None:
        return None
    seq_text = str(row[0])
    if not seq_text.isdigit():
        raise ValueError("audit event sequence high-water mark is invalid")
    seq = int(seq_text)
    if seq > 2**53 - 1:  # MAX_SAFE_INTEGER
        raise ValueError(
            "audit event sequence high-water mark exceeds the supported integer range"
        )
    return seq


def _restore_audit_event_sequence_high_water(
    conn: sqlite3.Connection, sequence: Optional[int]
) -> None:
    if sequence is None:
        return
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'audit_events'")
    conn.execute(
        "INSERT INTO sqlite_sequence (name, seq) VALUES ('audit_events', ?)",
        (sequence,),
    )


# ── Repair ────────────────────────────────────────────────


_LEGACY_V2_CREATE_AND_MIGRATE_SQL = """
CREATE TABLE audit_events_migration_new (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,
  source_id TEXT NOT NULL UNIQUE,
  schema_version INTEGER NOT NULL DEFAULT 1,
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
  tool_name TEXT,
  direction TEXT,
  channel TEXT,
  conversation_kind TEXT,
  message_outcome TEXT,
  reason_code TEXT,
  delivery_kind TEXT,
  failure_stage TEXT,
  duration_ms INTEGER,
  result_count INTEGER,
  account_ref TEXT,
  conversation_ref TEXT,
  message_ref TEXT,
  target_ref TEXT
);
INSERT INTO audit_events_migration_new (
  sequence,
  event_id,
  source_id,
  schema_version,
  source_sequence,
  occurred_at,
  kind,
  action,
  status,
  error_code,
  actor_type,
  actor_id,
  agent_id,
  session_key,
  session_id,
  run_id,
  tool_call_id,
  tool_name
)
SELECT
  sequence,
  event_id,
  source_id,
  1,
  source_sequence,
  occurred_at,
  kind,
  action,
  status,
  error_code,
  actor_type,
  actor_id,
  agent_id,
  session_key,
  session_id,
  run_id,
  tool_call_id,
  tool_name
FROM audit_events;
DROP TABLE audit_events;
ALTER TABLE audit_events_migration_new RENAME TO audit_events;
CREATE INDEX idx_audit_events_time
  ON audit_events(occurred_at DESC, sequence DESC);
CREATE INDEX idx_audit_events_agent_sequence
  ON audit_events(agent_id, sequence DESC);
CREATE INDEX idx_audit_events_session_sequence
  ON audit_events(session_key, sequence DESC);
CREATE INDEX idx_audit_events_run_sequence
  ON audit_events(run_id, sequence DESC);
CREATE INDEX idx_audit_events_kind_sequence
  ON audit_events(kind, sequence DESC);
CREATE INDEX idx_audit_events_status_sequence
  ON audit_events(status, sequence DESC);
CREATE INDEX idx_audit_events_channel_sequence
  ON audit_events(channel, sequence DESC);
CREATE INDEX idx_audit_events_direction_sequence
  ON audit_events(direction, sequence DESC);
CREATE TABLE IF NOT EXISTS audit_identity_keys (
  id INTEGER NOT NULL PRIMARY KEY CHECK (id = 1),
  key_id TEXT NOT NULL,
  key BLOB NOT NULL,
  created_at INTEGER NOT NULL
);
"""


def repair_audit_events_schema(conn: sqlite3.Connection) -> bool:
    """Rebuild a legacy ``audit_events`` table to the v2 shape.

    Mirrors ``repairAuditEventsSchema``. Returns ``True``
    when the table was rebuilt, ``False`` when no work was
    needed (or the table cannot be safely rebuilt).

    Callers are expected to wrap this in their own
    ``BEGIN IMMEDIATE`` transaction so the table swap +
    sequence restore roll back together on any error.
    """
    if has_canonical_audit_events_schema(conn):
        return False
    if not can_repair_legacy_audit_events_schema(conn):
        return False
    sequence_high_water = _read_audit_event_sequence_high_water(conn)
    # This is the only shipped legacy shape. The surrounding
    # transaction rolls the table swap + sequence restore
    # back together on any bad row.
    # ``can_repair_legacy_audit_events_schema`` refuses
    # foreign ``audit_events_migration_new`` tables, so this
    # CREATE never clobbers existing data.
    conn.executescript(_LEGACY_V2_CREATE_AND_MIGRATE_SQL)
    # AUTOINCREMENT is part of the stable cursor contract.
    # Rebuilding an empty or sparsely retained table must
    # not reuse a sequence already handed out.
    _restore_audit_event_sequence_high_water(conn, sequence_high_water)
    return True


__all__ = [
    "AUDIT_EVENT_LEGACY_COLUMNS",
    "AUDIT_EVENT_LEGACY_REQUIRED_NOT_NULL_COLUMNS",
    "AUDIT_EVENT_STATE_SCHEMA_VERSION",
    "AUDIT_EVENT_V2_COLUMNS",
    "AUDIT_EVENT_V2_REQUIRED_NOT_NULL_COLUMNS",
    "can_repair_legacy_audit_events_schema",
    "has_canonical_audit_events_schema",
    "repair_audit_events_schema",
]
