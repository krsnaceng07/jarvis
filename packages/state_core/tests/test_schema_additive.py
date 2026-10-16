"""Tests for ``jarvis_state_core.schema_additive``.

Covers:
- ``ensure_additive_state_columns`` is a no-op when every
  canonical table is missing (the function tolerates empty
  databases)
- the additive ensure adds every required column to a
  freshly-created canonical table
- the sequence backfill runs when ``diagnostic_events`` is
  populated
- the ``delivery_thread_id_type`` migration triggers when
  the column is freshly added
- the operator-approval resolution-ref namespace is wired
  through the additive ensure
"""

from __future__ import annotations

import sqlite3


from jarvis_state_core.schema_additive import ensure_additive_state_columns


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── no-op on empty database ─────────────────────────────────


def test_additive_noop_on_empty_db():
    """Every check is defensive: an empty DB does not error."""
    conn = _fresh_db()
    try:
        ensure_additive_state_columns(conn)  # no raise
    finally:
        conn.close()


# ── diagnostic_events sequence backfill ─────────────────────


def test_diagnostic_events_sequence_backfill_runs():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE diagnostic_events (
              scope TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );
            INSERT INTO diagnostic_events (scope, created_at) VALUES
              ('a', 1000),
              ('a', 2000),
              ('a', 2000),
              ('b', 1500);
            """
        )
        conn.commit()
        ensure_additive_state_columns(conn)
        # sequence is added; ROW_NUMBER() over (scope, created_at, rowid)
        # produces a stable 1..N per scope.
        rows = conn.execute(
            "SELECT scope, sequence FROM diagnostic_events ORDER BY scope, sequence"
        ).fetchall()
        seq_by_scope = {}
        for r in rows:
            seq_by_scope.setdefault(r["scope"], []).append(r["sequence"])
        assert seq_by_scope["a"] == [1, 2, 3]
        assert seq_by_scope["b"] == [1]
    finally:
        conn.close()


def test_diagnostic_events_sequence_idempotent_when_already_present():
    conn = _fresh_db()
    try:
        conn.execute(
            """
            CREATE TABLE diagnostic_events (
              scope TEXT NOT NULL,
              created_at INTEGER NOT NULL,
              sequence INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()
        # Second run: the column is already there, ensure is a no-op.
        ensure_additive_state_columns(conn)
        cols = conn.execute("PRAGMA table_info(diagnostic_events)").fetchall()
        assert any(c["name"] == "sequence" for c in cols)
    finally:
        conn.close()


# ── cron_run_logs additive ─────────────────────────────────


def test_cron_run_logs_adds_all_columns():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE cron_run_logs (id INTEGER)")
        conn.commit()
        ensure_additive_state_columns(conn)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(cron_run_logs)").fetchall()}
        # Spot-check a few representative columns.
        assert {"status", "error", "summary", "session_id", "entry_json"}.issubset(cols)
        assert "created_at" in cols
    finally:
        conn.close()


# ── cron_jobs additive + delivery_thread_id_type migration ─


def test_cron_jobs_adds_all_columns():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE cron_jobs (id INTEGER)")
        conn.commit()
        ensure_additive_state_columns(conn)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(cron_jobs)").fetchall()}
        for required in (
            "name",
            "enabled",
            "schedule_kind",
            "payload_kind",
            "delivery_thread_id",
            "delivery_thread_id_type",
            "state_json",
            "sort_order",
        ):
            assert required in cols, f"missing column: {required}"
    finally:
        conn.close()


def test_cron_jobs_delivery_thread_id_type_migration_runs():
    """The ``delivery_thread_id_type`` migration tags numeric thread IDs."""
    import json as _json

    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE cron_jobs (
              store_key TEXT, job_id TEXT, job_json TEXT,
              delivery_thread_id TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO cron_jobs (store_key, job_id, job_json, delivery_thread_id) "
            "VALUES (?, ?, ?, NULL)",
            ("k", "j1", _json.dumps({"delivery": {"threadId": 7}})),
        )
        conn.execute(
            "INSERT INTO cron_jobs (store_key, job_id, job_json, delivery_thread_id) "
            "VALUES (?, ?, ?, ?)",
            ("k", "j2", _json.dumps({"delivery": {"threadId": 42}}), "42"),
        )
        conn.commit()
        ensure_additive_state_columns(conn)
        rows = {
            r["job_id"]: r["delivery_thread_id_type"]
            for r in conn.execute(
                "SELECT job_id, delivery_thread_id_type FROM cron_jobs"
            ).fetchall()
        }
        assert rows["j1"] == "number"
        assert rows["j2"] == "number"
    finally:
        conn.close()


# ── task_runs requester_agent_id repair triggers backfill ─


def test_task_runs_adds_columns_and_runs_status_repair():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE task_runs (id INTEGER, delivery_status TEXT)")
        conn.execute(
            "INSERT INTO task_runs (id, delivery_status) "
            "VALUES (1, 'not-requested'), (2, 'delivered')"
        )
        conn.commit()
        ensure_additive_state_columns(conn)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(task_runs)").fetchall()}
        assert "requester_agent_id" in cols
        # Status repair normalizes 'not-requested'.
        statuses = {
            r["id"]: r["delivery_status"]
            for r in conn.execute("SELECT id, delivery_status FROM task_runs").fetchall()
        }
        assert statuses[1] == "not_applicable"
        assert statuses[2] == "delivered"
    finally:
        conn.close()


# ── operator-approval resolution-ref namespace ─────────────


def test_additive_ensure_wires_resolution_refs():
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
        conn.execute("INSERT INTO operator_approvals (approval_id, kind) VALUES ('a1', 'exec')")
        conn.commit()
        ensure_additive_state_columns(conn)
        row = conn.execute(
            "SELECT resolution_ref FROM operator_approvals WHERE approval_id = 'a1'"
        ).fetchone()
        assert row["resolution_ref"] is not None
        assert len(row["resolution_ref"]) == 43
    finally:
        conn.close()


# ── full pass over a minimal canonical-shape DB ───────────


def test_additive_ensure_idempotent_when_already_canonical():
    """A second run of the additive ensure must not re-add columns or
    re-run backfills.
    """
    conn = _fresh_db()
    try:
        # Seed every table the additive ensure touches in
        # canonical shape, then run the ensure twice.
        conn.executescript(
            """
            CREATE TABLE diagnostic_events (
              scope TEXT NOT NULL, created_at INTEGER NOT NULL,
              sequence INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE cron_run_logs (
              id INTEGER, status TEXT, entry_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE cron_jobs (
              id INTEGER, name TEXT NOT NULL DEFAULT '',
              schedule_kind TEXT NOT NULL DEFAULT 'manual',
              payload_kind TEXT NOT NULL DEFAULT 'message',
              delivery_thread_id_type TEXT
            );
            CREATE TABLE operator_approvals (
              approval_id TEXT NOT NULL,
              kind TEXT NOT NULL,
              PRIMARY KEY (approval_id)
            );
            """
        )
        conn.commit()
        ensure_additive_state_columns(conn)
        ensure_additive_state_columns(conn)
        # If columns are duplicated, the second call would
        # error; the no-op idempotence is the assertion.
    finally:
        conn.close()
