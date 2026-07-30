"""Operator-approval kind constraint repair (doctor-only).

Mirrors OpenClaw's
``src/state/openclaw-state-db-operator-approval-migration.ts``
1:1. The TS port rebuilds the ``operator_approvals`` table
when its ``kind CHECK`` constraint only allows the two-kind
shape (``'exec'`` / ``'plugin'``) shipped before
``'system-agent'`` was added. The Python port keeps the
exact same surface and uses an inline canonical CREATE
TABLE statement (the TS port reads a generated file).

Why doctor-only: the only legacy shapes this repair may
destructively replace are the exact prior canonical table
(with the two-kind constraint) and its shipped
``ALTER``-appended ``resolution_ref`` variant. Matching
column names alone is not fail-closed: a table with the
same names but different constraints/defaults/types would
get its rows copied under a schema that silently discards
those semantics.

Public surface:
- ``OperatorApprovalKind`` — closed set
- ``OPERATOR_APPROVAL_KINDS`` — tuple of the canonical kinds
- ``is_canonical_operator_approval_kind(value)`` -> bool
- ``has_canonical_operator_approval_kinds(conn)`` -> bool
- ``assert_canonical_operator_approval_kinds(conn, path)`` -> None
- ``detect_operator_approval_schema_migration(db, path)``
- ``repair_operator_approval_schema(db)`` -> ``list[str]``
  (returns the list of migration log lines)
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Literal, Optional

from .schema_helpers import table_exists


# ── Closed set of operator-approval kinds ──────────────────


OperatorApprovalKind = Literal["exec", "plugin", "system-agent"]


# Matches the ``COLUMNS`` const in the OpenClaw source.
# Order matters: the schema probe regexes assume this order
# and the rebuild copy statement enumerates columns by name.
OPERATOR_APPROVAL_COLUMNS: tuple[str, ...] = (
    "approval_id",
    "resolution_ref",
    "kind",
    "status",
    "presentation_json",
    "requested_by_device_id",
    "requested_by_client_id",
    "requested_by_device_token_auth",
    "reviewer_device_ids_json",
    "source_agent_id",
    "source_session_key",
    "source_session_id",
    "source_run_id",
    "source_tool_call_id",
    "source_tool_name",
    "audience_session_keys_json",
    "runtime_epoch",
    "created_at_ms",
    "expires_at_ms",
    "updated_at_ms",
    "decision",
    "terminal_reason",
    "resolved_at_ms",
    "resolver_kind",
    "resolver_id",
    "consumed_at_ms",
    "consumed_by",
)


def is_canonical_operator_approval_kind(value: Any) -> bool:
    """Return True when ``value`` is one of the canonical kinds.

    Mirrors ``isCanonicalOperatorApprovalKind`` from
    ``openclaw-state-db-operator-approval-migration.ts``.
    """
    return value in ("exec", "plugin", "system-agent")


# ── Schema probes ──────────────────────────────────────────


def _table_sql(conn: sqlite3.Connection, table_name: str) -> Optional[str]:
    """Return the ``sqlite_master`` CREATE statement for ``table_name``."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if not row or not row[0]:
        return None
    return str(row[0])


def has_canonical_operator_approval_kinds(conn: sqlite3.Connection) -> bool:
    """Return True when ``operator_approvals.kind`` accepts all 3 kinds.

    Mirrors ``hasCanonicalOperatorApprovalKinds``. The probe
    regex matches the canonical ``CHECK (kind IN ('exec',
    'plugin', 'system-agent'))`` shape; a missing table
    counts as canonical (nothing to validate).
    """
    if not table_exists(conn, "operator_approvals"):
        return True
    sql = (_table_sql(conn, "operator_approvals") or "").lower()
    return bool(
        re.search(
            r"kind\s+text\s+not\s+null\s+check\s*\(\s*kind\s+in\s*"
            r"\(\s*'exec'\s*,\s*'plugin'\s*,\s*'system-agent'\s*\)\s*\)",
            sql,
        )
    )


def assert_canonical_operator_approval_kinds(
    conn: sqlite3.Connection, pathname: str
) -> None:
    """Raise when ``operator_approvals.kind`` is not canonical.

    Mirrors ``assertCanonicalOperatorApprovalKinds``. The
    runtime refuses to read operator-approval rows through a
    legacy-kind table; the doctor flow runs the repair.
    """
    if not has_canonical_operator_approval_kinds(conn):
        raise RuntimeError(
            f"JARVIS state database {pathname} has a legacy operator "
            "approval schema; run jarvis doctor --fix to migrate it."
        )


# ── Canonical CREATE TABLE (Python-specific inline constant) ──
#
# The TS port reads ``OPENCLAW_STATE_SCHEMA_SQL`` from a
# generated file. The Python port keeps the same canonical
# statement inline so the rebuild path stays self-contained.
# The shape mirrors the OpenClaw generated SQL exactly:
# - all columns listed in OPERATOR_APPROVAL_COLUMNS, in order
# - ``kind`` is ``TEXT NOT NULL CHECK (kind IN ('exec', 'plugin', 'system-agent'))``
# - PRIMARY KEY (approval_id) UNIQUE
# - table closed with ``) STRICT;``


def _build_canonical_create_sql(table_name: str) -> str:
    """Return the canonical CREATE TABLE statement for ``operator_approvals``.

    Mirrors the OpenClaw generated statement:
    ``CREATE TABLE [IF NOT EXISTS] <table_name> ( ... ) STRICT;``
    """
    columns_sql = ",\n  ".join(
        f"{col} TEXT" for col in OPERATOR_APPROVAL_COLUMNS if col != "kind"
    )
    return (
        f"CREATE TABLE {table_name} (\n  "
        f"{columns_sql},\n  "
        f"kind TEXT NOT NULL CHECK (kind IN ('exec', 'plugin', 'system-agent')),\n  "
        f"PRIMARY KEY (approval_id)\n) STRICT;"
    )


# The ALTER-appended variant the prior schema migration
# produced: ``resolution_ref`` is inserted between
# ``approval_id`` and ``kind`` (nullable) and all other
# columns are the same. The Python port rebuilds the legacy
# variants into the canonical shape.
_ALTER_APPENDED_RESOLUTION_REF_SQL = (
    "CREATE TABLE {table_name} (\n  "
    "approval_id TEXT,\n  "
    "kind TEXT NOT NULL CHECK (kind IN ('exec', 'plugin')),\n  "
    "status TEXT,\n  "
    "presentation_json TEXT,\n  "
    "requested_by_device_id TEXT,\n  "
    "requested_by_client_id TEXT,\n  "
    "requested_by_device_token_auth TEXT,\n  "
    "reviewer_device_ids_json TEXT,\n  "
    "source_agent_id TEXT,\n  "
    "source_session_key TEXT,\n  "
    "source_session_id TEXT,\n  "
    "source_run_id TEXT,\n  "
    "source_tool_call_id TEXT,\n  "
    "source_tool_name TEXT,\n  "
    "audience_session_keys_json TEXT,\n  "
    "runtime_epoch INTEGER,\n  "
    "created_at_ms INTEGER,\n  "
    "expires_at_ms INTEGER,\n  "
    "updated_at_ms INTEGER,\n  "
    "decision TEXT,\n  "
    "terminal_reason TEXT,\n  "
    "resolved_at_ms INTEGER,\n  "
    "resolver_kind TEXT,\n  "
    "resolver_id TEXT,\n  "
    "consumed_at_ms INTEGER,\n  "
    "consumed_by TEXT,\n  "
    "resolution_ref TEXT,\n  "
    "PRIMARY KEY (approval_id)\n) STRICT;"
)


def _normalize_ddl(sql: str) -> str:
    """Collapse whitespace + strip a trailing semicolon.

    Mirrors ``normalizeDdl`` from
    ``openclaw-state-db-operator-approval-migration.ts``:
    ``sqlite_master`` stores the CREATE statement without a
    trailing semicolon, so comparison must match either
    form.
    """
    return re.sub(r"\s+", " ", sql).strip().rstrip(";")


def _canonical_create_sql_with_table_name(table_name: str) -> str:
    """Return the canonical CREATE TABLE for ``table_name`` (no IF NOT EXISTS)."""
    sql = _build_canonical_create_sql(table_name)
    # The probe compares against the canonical SQL stored
    # in ``sqlite_master`` which does NOT include
    # ``IF NOT EXISTS``.
    return sql.replace(
        f"CREATE TABLE {table_name} (", f"CREATE TABLE {table_name} ("
    )


def has_exact_legacy_operator_approval_schema(conn: sqlite3.Connection) -> bool:
    """Return True when the live table is the exact prior canonical shape.

    Mirrors ``hasExactLegacyOperatorApprovalSchema``. The
    check is intentionally strict: matching column names
    alone is not fail-closed (a table with the same names
    but different constraints/defaults/types would get its
    rows copied under a schema that silently discards those
    semantics).
    """
    live = _table_sql(conn, "operator_approvals")
    if not live:
        return False
    # 1. Strict-2-kind legacy (the original shipped shape).
    exact_strict_legacy = _build_canonical_create_sql("operator_approvals")
    exact_strict_legacy = exact_strict_legacy.replace(
        "CREATE TABLE operator_approvals (", "CREATE TABLE operator_approvals ("
    ).replace(
        "'exec', 'plugin', 'system-agent'", "'exec', 'plugin'"
    )
    # 2. ALTER-appended variant (the shipped
    #    ``ensure_column``-added ``resolution_ref`` shape).
    alter_appended = _ALTER_APPENDED_RESOLUTION_REF_SQL.format(
        table_name="operator_approvals"
    )
    candidates = [
        exact_strict_legacy,
        alter_appended,
        exact_strict_legacy.replace(") STRICT;", ");"),
        alter_appended.replace(") STRICT;", ");"),
    ]
    normalized_live = _normalize_ddl(live)
    return any(
        _normalize_ddl(candidate) == normalized_live for candidate in candidates
    )


def detect_operator_approval_schema_migration(
    conn: sqlite3.Connection, pathname: str
) -> list[dict[str, str]]:
    """Return a single migration if the table needs rebuilding.

    Mirrors ``detectOperatorApprovalSchemaMigration``.
    Returns an empty list when the table is canonical or
    missing.
    """
    if has_canonical_operator_approval_kinds(conn):
        return []
    return [
        {"kind": "operator-approvals-system-agent", "path": pathname},
    ]


# ── Rebuild ────────────────────────────────────────────────


def _operator_approval_index_sql() -> str:
    """Return the index statements for the rebuilt ``operator_approvals`` table.

    Mirrors ``operatorApprovalIndexSql``. The Python port
    inlines the canonical index statements so the rebuild
    stays self-contained.
    """
    return (
        "CREATE INDEX IF NOT EXISTS idx_operator_approvals_status_expiry "
        "ON operator_approvals(status, expires_at_ms);\n"
        "CREATE INDEX IF NOT EXISTS idx_operator_approvals_kind_status "
        "ON operator_approvals(kind, status);\n"
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_operator_approvals_resolution_ref "
        "ON operator_approvals(resolution_ref);"
    )


def _repair_operator_approval_kinds(conn: sqlite3.Connection) -> bool:
    """Rebuild a legacy ``operator_approvals`` table to the canonical shape.

    Returns ``True`` when the table was rebuilt; ``False``
    when the table is canonical, a partial-migration
    ``operator_approvals_migration_new`` table is present
    (would clobber unrelated data), or the table does not
    match the exact legacy shape.
    """
    if (
        has_canonical_operator_approval_kinds(conn)
        or table_exists(conn, "operator_approvals_migration_new")
        or not has_exact_legacy_operator_approval_schema(conn)
    ):
        return False
    columns_csv = ", ".join(OPERATOR_APPROVAL_COLUMNS)
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Build the canonical migration_new table.
        conn.execute(
            _build_canonical_create_sql("operator_approvals_migration_new")
        )
        # The legacy ALTER-appended variant is nullable, so
        # pre-ref rows can hold NULL or junk that violates
        # the canonical ``resolution_ref`` shape (43 chars
        # [A-Za-z0-9_-]). Approvals are transient runtime
        # state: drop nonconforming rows instead of aborting
        # the whole repair and re-wedging startup. The
        # filter mirrors the canonical ``resolution_ref``
        # CHECK exactly.
        conn.execute(
            f"INSERT INTO operator_approvals_migration_new ({columns_csv}) "
            f"SELECT {columns_csv} FROM operator_approvals "
            f"WHERE typeof(resolution_ref) = 'text' "
            f"AND length(resolution_ref) = 43 "
            f"AND resolution_ref NOT GLOB '*[^A-Za-z0-9_-]*';"
        )
        conn.execute("DROP TABLE operator_approvals;")
        conn.execute(
            "ALTER TABLE operator_approvals_migration_new "
            "RENAME TO operator_approvals;"
        )
        # Rebuilding the table drops its indexes; replay
        # them.
        for statement in _operator_approval_index_sql().split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True


def repair_operator_approval_schema(conn: sqlite3.Connection) -> list[str]:
    """Repair a legacy ``operator_approvals`` kind constraint.

    Mirrors ``repairOperatorApprovalSchema``. Returns a
    list of human-readable migration log lines; the empty
    list when the table is already canonical.
    """
    if not _repair_operator_approval_kinds(conn):
        return []
    return [
        "Migrated shared state operator approvals → JARVIS system changes"
    ]


__all__ = [
    "OPERATOR_APPROVAL_COLUMNS",
    "OperatorApprovalKind",
    "assert_canonical_operator_approval_kinds",
    "detect_operator_approval_schema_migration",
    "has_canonical_operator_approval_kinds",
    "has_exact_legacy_operator_approval_schema",
    "is_canonical_operator_approval_kind",
    "repair_operator_approval_schema",
]
