"""Tests for ``jarvis_state_core.schema_helpers``.

Covers:
- table_exists on missing + present tables
- table_has_column with case-sensitive column name
- table_primary_key_columns returns PK in declaration order
- ensure_column adds a column when missing; no-op when present
- ensure_column refuses when the table is missing
- index_exists + table_index_list
"""
from __future__ import annotations

import sqlite3


from jarvis_state_core.schema_helpers import (
    ensure_column,
    index_exists,
    table_exists,
    table_has_column,
    table_index_list,
    table_primary_key_columns,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── table_exists ───────────────────────────────────────────


def test_table_exists_returns_false_for_missing_table():
    conn = _fresh_db()
    try:
        assert table_exists(conn, "no_such") is False
    finally:
        conn.close()


def test_table_exists_returns_true_for_present_table():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        assert table_exists(conn, "foo") is True
    finally:
        conn.close()


# ── table_has_column ───────────────────────────────────────


def test_table_has_column_returns_true_for_existing_column():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER, name TEXT)")
        assert table_has_column(conn, "foo", "id") is True
        assert table_has_column(conn, "foo", "name") is True
    finally:
        conn.close()


def test_table_has_column_returns_false_for_missing_column():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        assert table_has_column(conn, "foo", "missing") is False
    finally:
        conn.close()


def test_table_has_column_is_case_sensitive():
    conn = _fresh_db()
    try:
        conn.execute('CREATE TABLE foo ("UserId" INTEGER)')
        assert table_has_column(conn, "foo", "UserId") is True
        assert table_has_column(conn, "foo", "userid") is False
    finally:
        conn.close()


# ── table_primary_key_columns ──────────────────────────────


def test_table_primary_key_columns_for_composite_pk():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE foo (a TEXT NOT NULL, b TEXT NOT NULL, "
            "PRIMARY KEY (a, b))"
        )
        assert table_primary_key_columns(conn, "foo") == ["a", "b"]
    finally:
        conn.close()


def test_table_primary_key_columns_for_single_pk():
    conn = _fresh_db()
    try:
        conn.execute(
            "CREATE TABLE foo (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)"
        )
        assert table_primary_key_columns(conn, "foo") == ["id"]
    finally:
        conn.close()


def test_table_primary_key_columns_for_missing_table():
    conn = _fresh_db()
    try:
        assert table_primary_key_columns(conn, "no_such") == []
    finally:
        conn.close()


# ── ensure_column ──────────────────────────────────────────


def test_ensure_column_adds_missing_column():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        assert ensure_column(conn, "foo", "name TEXT") is True
        assert table_has_column(conn, "foo", "name") is True
    finally:
        conn.close()


def test_ensure_column_is_noop_when_column_exists():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER, name TEXT)")
        assert ensure_column(conn, "foo", "name TEXT") is False
    finally:
        conn.close()


def test_ensure_column_refuses_missing_table():
    conn = _fresh_db()
    try:
        # No table at all; ensure_column should refuse.
        assert ensure_column(conn, "no_such", "name TEXT") is False
    finally:
        conn.close()


def test_ensure_column_preserves_existing_rows():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        conn.execute("INSERT INTO foo (id) VALUES (1)")
        conn.commit()
        assert ensure_column(conn, "foo", "name TEXT NOT NULL DEFAULT 'anon'") is True
        row = conn.execute("SELECT name FROM foo WHERE id = 1").fetchone()
        assert row["name"] == "anon"
    finally:
        conn.close()


def test_ensure_column_uses_first_token_as_column_name():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        # ``column_sql`` can have many tokens (type, default, check).
        # The first whitespace-delimited token is the column name.
        assert ensure_column(
            conn, "foo", "score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0)"
        ) is True
        assert table_has_column(conn, "foo", "score") is True
    finally:
        conn.close()


# ── table_index_list + index_exists ───────────────────────


def test_table_index_list_empty_when_no_indexes():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER)")
        assert table_index_list(conn, "foo") == []
    finally:
        conn.close()


def test_table_index_list_returns_index_names():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER, name TEXT)")
        conn.execute("CREATE INDEX idx_foo_name ON foo(name)")
        conn.commit()
        assert "idx_foo_name" in table_index_list(conn, "foo")
    finally:
        conn.close()


def test_index_exists_for_present_index():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE foo (id INTEGER, name TEXT)")
        conn.execute("CREATE INDEX idx_foo_name ON foo(name)")
        conn.commit()
        assert index_exists(conn, "idx_foo_name") is True
        assert index_exists(conn, "no_such_idx") is False
    finally:
        conn.close()


def test_table_index_list_empty_for_missing_table():
    conn = _fresh_db()
    try:
        assert table_index_list(conn, "no_such") == []
    finally:
        conn.close()
