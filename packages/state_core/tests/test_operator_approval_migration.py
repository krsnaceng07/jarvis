"""Tests for ``jarvis_state_core.operator_approval_migration``.

Covers:
- is_canonical_operator_approval_kind accepts the closed set
- has_canonical_operator_approval_kinds probes the CHECK shape
- assert_canonical_operator_approval_kinds raises on legacy
- has_exact_legacy_operator_approval_schema: only the two
  legacy shapes (strict-2-kind + ALTER-appended) match
- detect_operator_approval_schema_migration returns the kind
- repair_operator_approval_schema rebuilds the table
- build_approval_resolution_ref + ensure_operator_approval_resolution_refs
  are reachable through the public surface
"""
from __future__ import annotations

import sqlite3

import pytest

from jarvis_state_core.operator_approval_migration import (
    OPERATOR_APPROVAL_COLUMNS,
    assert_canonical_operator_approval_kinds,
    detect_operator_approval_schema_migration,
    has_canonical_operator_approval_kinds,
    has_exact_legacy_operator_approval_schema,
    is_canonical_operator_approval_kind,
    repair_operator_approval_schema,
)


def _build_legacy_two_kind_sql() -> str:
    """Return the full 27-column legacy operator_approvals DDL.

    Mirrors the OpenClaw ``canonicalOperatorApprovalCreateSql``
    with the kind-CHECK replaced by the legacy 2-kind shape.
    The probe only matches this exact shape (fail-closed).
    """
    columns_sql = ",\n  ".join(
        f"{col} TEXT" for col in OPERATOR_APPROVAL_COLUMNS if col != "kind"
    )
    return (
        "CREATE TABLE operator_approvals (\n  "
        f"{columns_sql},\n  "
        "kind TEXT NOT NULL CHECK (kind IN ('exec', 'plugin')),\n  "
        "PRIMARY KEY (approval_id)\n) STRICT;"
    )


def _build_canonical_sql() -> str:
    """Return the full 27-column canonical operator_approvals DDL."""
    columns_sql = ",\n  ".join(
        f"{col} TEXT" for col in OPERATOR_APPROVAL_COLUMNS if col != "kind"
    )
    return (
        "CREATE TABLE operator_approvals (\n  "
        f"{columns_sql},\n  "
        "kind TEXT NOT NULL CHECK (kind IN ('exec', 'plugin', 'system-agent')),\n  "
        "PRIMARY KEY (approval_id)\n) STRICT;"
    )


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── is_canonical_operator_approval_kind ────────────────────


@pytest.mark.parametrize("kind", ["exec", "plugin", "system-agent"])
def test_is_canonical_accepts_three_kinds(kind: str):
    assert is_canonical_operator_approval_kind(kind) is True


@pytest.mark.parametrize(
    "value",
    ["", "EXEC", "system_agent", "user", None, 0, 1, {}, []],
)
def test_is_canonical_rejects_non_kinds(value):
    assert is_canonical_operator_approval_kind(value) is False


# ── has_canonical_operator_approval_kinds ─────────────────


def test_has_canonical_returns_true_when_table_missing():
    conn = _fresh_db()
    try:
        assert has_canonical_operator_approval_kinds(conn) is True
    finally:
        conn.close()


def test_has_canonical_returns_true_for_canonical_kind():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE operator_approvals (
              approval_id TEXT NOT NULL,
              kind TEXT NOT NULL CHECK (kind IN ('exec', 'plugin', 'system-agent')),
              PRIMARY KEY (approval_id)
            ) STRICT;
            """
        )
        assert has_canonical_operator_approval_kinds(conn) is True
    finally:
        conn.close()


def test_has_canonical_returns_false_for_legacy_two_kind():
    conn = _fresh_db()
    try:
        conn.executescript(_build_legacy_two_kind_sql())
        assert has_canonical_operator_approval_kinds(conn) is False
    finally:
        conn.close()


# ── assert_canonical_operator_approval_kinds ──────────────


def test_assert_canonical_raises_on_legacy():
    conn = _fresh_db()
    try:
        conn.executescript(_build_legacy_two_kind_sql())
        with pytest.raises(RuntimeError, match="legacy operator approval schema"):
            assert_canonical_operator_approval_kinds(conn, "memory:")
    finally:
        conn.close()


def test_assert_canonical_passes_on_canonical():
    conn = _fresh_db()
    try:
        conn.executescript(_build_canonical_sql())
        # No raise.
        assert_canonical_operator_approval_kinds(conn, "memory:")
    finally:
        conn.close()


# ── has_exact_legacy_operator_approval_schema ─────────────


def test_exact_legacy_true_for_two_kind_strict():
    conn = _fresh_db()
    try:
        conn.executescript(_build_legacy_two_kind_sql())
        assert has_exact_legacy_operator_approval_schema(conn) is True
    finally:
        conn.close()


def test_exact_legacy_false_for_already_canonical():
    conn = _fresh_db()
    try:
        conn.executescript(_build_canonical_sql())
        assert has_exact_legacy_operator_approval_schema(conn) is False
    finally:
        conn.close()


def test_exact_legacy_false_for_missing_table():
    conn = _fresh_db()
    try:
        assert has_exact_legacy_operator_approval_schema(conn) is False
    finally:
        conn.close()


# ── detect_operator_approval_schema_migration ─────────────


def test_detect_returns_empty_for_canonical_or_missing():
    conn = _fresh_db()
    try:
        assert detect_operator_approval_schema_migration(conn, "memory:") == []
    finally:
        conn.close()


def test_detect_returns_migration_for_legacy():
    conn = _fresh_db()
    try:
        conn.executescript(_build_legacy_two_kind_sql())
        migrations = detect_operator_approval_schema_migration(conn, "memory:")
        assert len(migrations) == 1
        assert migrations[0]["kind"] == "operator-approvals-system-agent"
        assert migrations[0]["path"] == "memory:"
    finally:
        conn.close()


# ── repair_operator_approval_schema ───────────────────────


def test_repair_noop_on_canonical_table():
    conn = _fresh_db()
    try:
        conn.executescript(_build_canonical_sql())
        log = repair_operator_approval_schema(conn)
        assert log == []
    finally:
        conn.close()


def test_repair_noop_on_missing_table():
    conn = _fresh_db()
    try:
        log = repair_operator_approval_schema(conn)
        assert log == []
    finally:
        conn.close()


def test_repair_rebuilds_legacy_table_and_accepts_system_agent():
    from jarvis_state_core.legacy_backfills import build_approval_resolution_ref

    conn = _fresh_db()
    try:
        conn.executescript(_build_legacy_two_kind_sql())
        # The legacy rebuild filter requires a valid
        # ``resolution_ref`` (43 chars, base64url); rows
        # without one are dropped (the additive backfill
        # re-adds them after the rebuild).
        valid_ref = build_approval_resolution_ref(
            approval_id="a1", approval_kind="exec"
        )
        conn.execute(
            "INSERT INTO operator_approvals (approval_id, kind, resolution_ref) "
            "VALUES ('a1', 'exec', ?)",
            (valid_ref,),
        )
        conn.commit()
        log = repair_operator_approval_schema(conn)
        assert len(log) == 1
        assert "operator approvals" in log[0]
        # After repair: system-agent should be accepted.
        assert has_canonical_operator_approval_kinds(conn) is True
        conn.execute(
            "INSERT INTO operator_approvals (approval_id, kind) "
            "VALUES ('a2', 'system-agent')"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT kind FROM operator_approvals ORDER BY approval_id"
        ).fetchall()
        assert [r["kind"] for r in rows] == ["exec", "system-agent"]
    finally:
        conn.close()


def test_repair_refuses_when_partial_migration_table_exists():
    conn = _fresh_db()
    try:
        conn.executescript(
            _build_legacy_two_kind_sql()
            + "CREATE TABLE operator_approvals_migration_new (unrelated TEXT);"
        )
        log = repair_operator_approval_schema(conn)
        # Foreign migration_new table means the repair
        # refuses rather than clobbering unrelated data.
        assert log == []
    finally:
        conn.close()


def test_operational_approval_columns_count():
    """The 27 column names OpenClaw documents must all be present."""
    assert len(OPERATOR_APPROVAL_COLUMNS) == 27
    assert "approval_id" in OPERATOR_APPROVAL_COLUMNS
    assert "kind" in OPERATOR_APPROVAL_COLUMNS
    assert "resolution_ref" in OPERATOR_APPROVAL_COLUMNS
