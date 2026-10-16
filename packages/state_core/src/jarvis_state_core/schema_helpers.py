"""Shared SQLite schema probes + additive column helpers.

Mirrors OpenClaw's
``src/state/openclaw-state-db-schema-helpers.ts`` 1:1. The
Python port exposes the same four operations the TS port
does:

- ``table_has_column`` — does the table contain the column
- ``table_primary_key_columns`` — primary-key columns in
  declaration order
- ``table_exists`` — does the table exist in
  ``sqlite_master``
- ``ensure_column`` — additive ``ALTER TABLE ADD COLUMN``;
  no-op when the column is already present

State migrations are additive here; destructive or
shape-changing repairs belong in doctor. The function
refuses to add a column when the table is missing (the
``ensure_*`` flow that bootstraps the table runs first).

Public surface:
- ``table_has_column(conn, table, column)`` -> ``bool``
- ``table_primary_key_columns(conn, table)`` -> ``list[str]``
- ``table_exists(conn, table)`` -> ``bool``
- ``ensure_column(conn, table, column_sql)`` -> ``bool``
- ``table_index_list(conn, table)`` -> ``list[str]`` (used
  by other modules; not in the OpenClaw helper but matches
  the same probe style)
- ``index_exists(conn, index)`` -> ``bool``
"""

from __future__ import annotations

import sqlite3
from typing import Any


def _table_column_info(conn: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    """Return the ``PRAGMA table_info`` rows for a table as plain dicts.

    Mirrors the row shape OpenClaw reads: ``name``, ``pk``.
    The Python port also keeps ``type``, ``notnull``,
    ``default`` for richer probes.
    """
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


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Return True when ``table_name`` exists in ``sqlite_master``.

    Mirrors ``tableExists`` from
    ``openclaw-state-db-schema-helpers.ts``.
    """
    row = conn.execute(
        "SELECT 1 AS ok FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row and row[0] == 1)


def table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Return True when ``table_name`` has a column named ``column_name``.

    Mirrors ``tableHasColumn`` from
    ``openclaw-state-db-schema-helpers.ts``. The probe is
    case-sensitive on the column name (matches the SQLite
    default and the OpenClaw probe).
    """
    return any(column.get("name") == column_name for column in _table_column_info(conn, table_name))


def table_primary_key_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    """Return the primary-key columns for ``table_name`` in declaration order.

    Mirrors ``tablePrimaryKeyColumns`` from
    ``openclaw-state-db-schema-helpers.ts``. The TS port uses
    ``toSorted`` (stable) on the ``pk`` ordinal; the Python
    port uses ``sorted`` with the same key, which is
    stable for equal keys in CPython 3.7+.
    """
    if not table_exists(conn, table_name):
        return []
    return [
        column["name"]
        for column in sorted(
            _table_column_info(conn, table_name),
            key=lambda c: int(c.get("pk") or 0),
        )
        if int(column.get("pk") or 0) > 0 and isinstance(column.get("name"), str)
    ]


def ensure_column(conn: sqlite3.Connection, table_name: str, column_sql: str) -> bool:
    """Run ``ALTER TABLE <table> ADD COLUMN <column_sql>`` if needed.

    Mirrors ``ensureColumn`` from
    ``openclaw-state-db-schema-helpers.ts``. Returns True
    when the column was added; False when the table is
    missing, the column already exists, or the column
    spec is empty.

    The Python port parses the column name from the first
    whitespace-delimited token of ``column_sql`` (matches
    the TS regex ``columnSql.trim().split(/\\s+/, 1)[0]``).
    State migrations are additive here; destructive or
    shape-changing repairs belong in doctor.
    """
    column_name = column_sql.strip().split(None, 1)[0] if column_sql.strip() else ""
    if (
        not column_name
        or not table_exists(conn, table_name)
        or table_has_column(conn, table_name, column_name)
    ):
        return False
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")
    return True


def table_index_list(conn: sqlite3.Connection, table_name: str) -> list[str]:
    """Return the index names attached to ``table_name``.

    Python-specific helper (not a 1:1 mirror of an OpenClaw
    helper) that the agent-databases primary-key repair +
    audit-event + operator-approval modules share. Returns
    the empty list when the table is missing.

    ``PRAGMA index_list`` columns: ``seq, name, unique,
    origin, partial``.
    """
    if not table_exists(conn, table_name):
        return []
    rows = conn.execute(f"PRAGMA index_list({table_name})").fetchall()
    return [str(row[1]) for row in rows if row and row[1] is not None]


def index_exists(conn: sqlite3.Connection, index_name: str) -> bool:
    """Return True when ``index_name`` exists in ``sqlite_master``.

    Python-specific helper that mirrors the
    ``sqlite_master`` style probe used elsewhere in the
    state core (the OpenClaw source uses ad-hoc index
    probes; this consolidates the pattern).
    """
    row = conn.execute(
        "SELECT 1 AS ok FROM sqlite_master WHERE type = 'index' AND name = ?",
        (index_name,),
    ).fetchone()
    return bool(row and row[0] == 1)


__all__ = [
    "ensure_column",
    "index_exists",
    "table_exists",
    "table_has_column",
    "table_index_list",
    "table_primary_key_columns",
]
