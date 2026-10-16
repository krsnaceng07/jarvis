"""Tests for ``jarvis_state_core.legacy_backfills``.

Covers:
- backfill_acp_replay_estimated_bytes (skips when no work)
- backfill_cron_run_log_entry_json
- migrate_legacy_cron_delivery_thread_ids
- repair_legacy_task_agent_attribution (no-op when table
  or column is missing)
- repair_legacy_task_delivery_statuses (canonicalizes
  'not-requested' to 'not_applicable')
- backfill_cron_jobs_from_job_json
- backfill_delivery_queue_entries_from_entry_json
- build_approval_resolution_ref
- ensure_operator_approval_resolution_refs
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from jarvis_state_core.legacy_backfills import (
    backfill_acp_replay_estimated_bytes,
    backfill_cron_jobs_from_job_json,
    backfill_cron_run_log_entry_json,
    backfill_delivery_queue_entries_from_entry_json,
    build_approval_resolution_ref,
    ensure_operator_approval_resolution_refs,
    migrate_legacy_cron_delivery_thread_ids,
    repair_legacy_task_agent_attribution,
    repair_legacy_task_delivery_statuses,
)
from jarvis_state_core.operator_approval_migration import (
    is_canonical_operator_approval_kind,
)


def _fresh_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


# ── backfill_acp_replay_estimated_bytes ────────────────────


def test_acp_replay_noop_when_tables_missing():
    conn = _fresh_db()
    try:
        backfill_acp_replay_estimated_bytes(conn)  # no raise
    finally:
        conn.close()


def test_acp_replay_computes_estimated_bytes_from_lengths():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE acp_replay_events (
              session_id TEXT,
              session_key TEXT,
              update_json TEXT,
              run_id TEXT,
              estimated_bytes INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE acp_replay_sessions (
              session_id TEXT,
              session_key TEXT,
              cwd TEXT,
              estimated_bytes INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            "INSERT INTO acp_replay_events "
            "(session_id, session_key, update_json, run_id, estimated_bytes) "
            "VALUES (?, ?, ?, ?, 0)",
            ("s", "k", "u", "r"),
        )
        conn.execute(
            "INSERT INTO acp_replay_sessions "
            "(session_id, session_key, cwd, estimated_bytes) "
            "VALUES (?, ?, ?, 0)",
            ("s", "k", "/tmp/cwd"),
        )
        conn.commit()
        backfill_acp_replay_estimated_bytes(conn)
        ev = conn.execute("SELECT estimated_bytes FROM acp_replay_events").fetchone()
        se = conn.execute("SELECT estimated_bytes FROM acp_replay_sessions").fetchone()
        # length("s") + length("k") + length("u") + length("r") + 32
        assert ev["estimated_bytes"] == 1 + 1 + 1 + 1 + 32
        # length("s") + length("k") + length("/tmp/cwd") + 32 + 36 (event total)
        assert se["estimated_bytes"] == 1 + 1 + 8 + 32 + 36
    finally:
        conn.close()


# ── backfill_cron_run_log_entry_json ───────────────────────


def test_cron_run_log_noop_when_table_missing():
    conn = _fresh_db()
    try:
        backfill_cron_run_log_entry_json(conn)  # no raise
    finally:
        conn.close()


def test_cron_run_log_fills_entry_json_from_columns():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE cron_run_logs (
              store_key TEXT NOT NULL,
              job_id TEXT NOT NULL,
              seq INTEGER NOT NULL,
              ts INTEGER NOT NULL,
              entry_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )
        conn.execute(
            "INSERT INTO cron_run_logs (store_key, job_id, seq, ts, entry_json) "
            "VALUES ('k', 'j1', 1, 1000, '{}')"
        )
        conn.commit()
        backfill_cron_run_log_entry_json(conn)
        row = conn.execute("SELECT entry_json FROM cron_run_logs").fetchone()
        payload = json.loads(row["entry_json"])
        assert payload == {"ts": 1000, "jobId": "j1", "action": "finished"}
    finally:
        conn.close()


# ── migrate_legacy_cron_delivery_thread_ids ────────────────


def test_migrate_cron_delivery_thread_ids_noop_when_no_legacy():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE cron_jobs (
              store_key TEXT,
              job_id TEXT,
              job_json TEXT,
              delivery_thread_id TEXT,
              delivery_thread_id_type TEXT
            );
            """
        )
        conn.execute("INSERT INTO cron_jobs VALUES ('k', 'j', '{}', 't1', 'string')")
        conn.commit()
        migrate_legacy_cron_delivery_thread_ids(conn)
        row = conn.execute(
            "SELECT delivery_thread_id, delivery_thread_id_type FROM cron_jobs"
        ).fetchone()
        assert row["delivery_thread_id_type"] == "string"
    finally:
        conn.close()


def test_migrate_cron_delivery_thread_ids_recovers_numeric_from_job_json():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE cron_jobs (
              store_key TEXT,
              job_id TEXT,
              job_json TEXT,
              delivery_thread_id TEXT,
              delivery_thread_id_type TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO cron_jobs (store_key, job_id, job_json, delivery_thread_id, delivery_thread_id_type) "
            "VALUES ('k', 'j', ?, NULL, NULL)",
            (json.dumps({"delivery": {"threadId": 42}}),),
        )
        conn.commit()
        migrate_legacy_cron_delivery_thread_ids(conn)
        row = conn.execute(
            "SELECT delivery_thread_id, delivery_thread_id_type FROM cron_jobs"
        ).fetchone()
        assert row["delivery_thread_id"] == "42"
        assert row["delivery_thread_id_type"] == "number"
    finally:
        conn.close()


# ── repair_legacy_task_agent_attribution ───────────────────


def test_task_agent_attribution_noop_when_table_missing():
    conn = _fresh_db()
    try:
        repair_legacy_task_agent_attribution(conn)  # no raise
    finally:
        conn.close()


def test_task_agent_attribution_noop_when_column_missing():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE task_runs (id INTEGER)")
        conn.commit()
        repair_legacy_task_agent_attribution(conn)  # no raise
    finally:
        conn.close()


# ── repair_legacy_task_delivery_statuses ──────────────────


def test_task_delivery_statuses_canonicalizes_not_requested():
    conn = _fresh_db()
    try:
        conn.execute("CREATE TABLE task_runs (id INTEGER, delivery_status TEXT)")
        conn.execute(
            "INSERT INTO task_runs (id, delivery_status) "
            "VALUES (1, 'not-requested'), (2, 'delivered'), (3, NULL)"
        )
        conn.commit()
        repair_legacy_task_delivery_statuses(conn)
        rows = conn.execute("SELECT id, delivery_status FROM task_runs ORDER BY id").fetchall()
        statuses = {r["id"]: r["delivery_status"] for r in rows}
        assert statuses[1] == "not_applicable"
        assert statuses[2] == "delivered"
        assert statuses[3] is None
    finally:
        conn.close()


# ── backfill_cron_jobs_from_job_json ──────────────────────


def test_cron_jobs_from_job_json_noop_when_table_missing():
    conn = _fresh_db()
    try:
        backfill_cron_jobs_from_job_json(conn)  # no raise
    finally:
        conn.close()


def test_cron_jobs_from_job_json_projects_cron_schedule():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE cron_jobs (
              store_key TEXT, job_id TEXT, job_json TEXT,
              updated_at INTEGER, schedule_kind TEXT, payload_kind TEXT,
              name TEXT, created_at_ms INTEGER, agent_id TEXT, session_key TEXT,
              schedule_expr TEXT, schedule_tz TEXT, every_ms INTEGER,
              anchor_ms INTEGER, at TEXT, stagger_ms INTEGER,
              session_target TEXT, wake_mode TEXT, payload_message TEXT,
              payload_model TEXT, payload_fallbacks_json TEXT,
              payload_thinking TEXT, payload_timeout_seconds INTEGER,
              payload_allow_unsafe_external_content INTEGER,
              payload_external_content_source_json TEXT,
              payload_light_context INTEGER, payload_tools_allow_json TEXT,
              delivery_mode TEXT, delivery_channel TEXT,
              delivery_to TEXT, delivery_thread_id TEXT,
              delivery_account_id TEXT, delivery_best_effort INTEGER,
              delivery_completion_mode TEXT, delivery_completion_to TEXT,
              failure_delivery_mode TEXT, failure_delivery_channel TEXT,
              failure_delivery_to TEXT, failure_delivery_account_id TEXT,
              failure_alert_disabled INTEGER, failure_alert_after INTEGER,
              failure_alert_channel TEXT, failure_alert_to TEXT,
              failure_alert_cooldown_ms INTEGER,
              failure_alert_include_skipped INTEGER,
              failure_alert_mode TEXT, failure_alert_account_id TEXT,
              enabled INTEGER, delete_after_run INTEGER,
              runtime_updated_at_ms INTEGER
            );
            """
        )
        job = {
            "name": "morning-checkin",
            "enabled": True,
            "deleteAfterRun": False,
            "createdAtMs": 1700000000000,
            "agentId": "main",
            "sessionKey": "agent:main:main",
            "schedule": {
                "kind": "cron",
                "expr": "0 9 * * *",
                "tz": "America/New_York",
                "staggerMs": 0,
            },
            "payload": {
                "kind": "agentTurn",
                "message": "good morning",
                "model": "sonnet",
                "fallbacks": ["haiku"],
                "thinking": "off",
                "timeoutSeconds": 60,
            },
            "delivery": {
                "mode": "announce",
                "channel": "telegram",
                "to": "self",
                "threadId": "t-1",
                "accountId": "acc-1",
                "bestEffort": True,
            },
        }
        conn.execute(
            "INSERT INTO cron_jobs (store_key, job_id, job_json, updated_at, "
            "schedule_kind, payload_kind) VALUES (?, ?, ?, ?, 'manual', 'message')",
            ("store-1", "job-1", json.dumps(job), 1700000050000),
        )
        conn.commit()
        backfill_cron_jobs_from_job_json(conn)
        row = conn.execute(
            "SELECT name, enabled, schedule_kind, schedule_expr, schedule_tz, "
            "stagger_ms, payload_kind, payload_message, payload_model, "
            "payload_fallbacks_json, delivery_mode, delivery_channel, "
            "delivery_to, delivery_thread_id, delivery_account_id, "
            "delivery_best_effort "
            "FROM cron_jobs"
        ).fetchone()
        assert row["name"] == "morning-checkin"
        assert row["enabled"] == 1
        assert row["schedule_kind"] == "cron"
        assert row["schedule_expr"] == "0 9 * * *"
        assert row["schedule_tz"] == "America/New_York"
        assert row["stagger_ms"] == 0
        assert row["payload_kind"] == "agentTurn"
        assert row["payload_message"] == "good morning"
        assert row["payload_model"] == "sonnet"
        assert json.loads(row["payload_fallbacks_json"]) == ["haiku"]
        assert row["delivery_mode"] == "announce"
        assert row["delivery_channel"] == "telegram"
        assert row["delivery_to"] == "self"
        assert row["delivery_thread_id"] == "t-1"
        assert row["delivery_account_id"] == "acc-1"
        assert row["delivery_best_effort"] == 1
    finally:
        conn.close()


# ── backfill_delivery_queue_entries_from_entry_json ───────


def test_delivery_queue_noop_when_table_missing():
    conn = _fresh_db()
    try:
        backfill_delivery_queue_entries_from_entry_json(conn)  # no raise
    finally:
        conn.close()


def test_delivery_queue_projects_route_from_entry_json():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE delivery_queue_entries (
              queue_name TEXT, id TEXT, entry_json TEXT,
              status TEXT, retry_count INTEGER NOT NULL DEFAULT 0,
              last_attempt_at INTEGER, last_error TEXT,
              recovery_state TEXT, platform_send_started_at INTEGER,
              entry_kind TEXT, session_key TEXT, channel TEXT,
              target TEXT, account_id TEXT
            );
            """
        )
        entry = {
            "kind": "message",
            "sessionKey": "agent:main:main",
            "route": {"channel": "telegram", "to": "u1", "accountId": "acc-x"},
            "retryCount": 3,
            "lastAttemptAt": 1700000000000,
            "lastError": "rate-limited",
            "recoveryState": "queued",
            "platformSendStartedAt": 1700000001000,
        }
        conn.execute(
            "INSERT INTO delivery_queue_entries (queue_name, id, entry_json, status) "
            "VALUES ('main', 'q1', ?, 'pending')",
            (json.dumps(entry),),
        )
        conn.commit()
        backfill_delivery_queue_entries_from_entry_json(conn)
        row = conn.execute(
            "SELECT entry_kind, session_key, channel, target, account_id, "
            "retry_count, last_attempt_at, last_error, recovery_state, "
            "platform_send_started_at "
            "FROM delivery_queue_entries"
        ).fetchone()
        assert row["entry_kind"] == "message"
        assert row["session_key"] == "agent:main:main"
        assert row["channel"] == "telegram"
        assert row["target"] == "u1"
        assert row["account_id"] == "acc-x"
        assert row["retry_count"] == 3
        assert row["last_attempt_at"] == 1700000000000
        assert row["last_error"] == "rate-limited"
        assert row["recovery_state"] == "queued"
        assert row["platform_send_started_at"] == 1700000001000
    finally:
        conn.close()


# ── build_approval_resolution_ref ─────────────────────────


def test_build_approval_resolution_ref_is_deterministic():
    ref1 = build_approval_resolution_ref(approval_id="ap-1", approval_kind="exec")
    ref2 = build_approval_resolution_ref(approval_id="ap-1", approval_kind="exec")
    assert ref1 == ref2
    assert len(ref1) == 43
    # The set of allowed characters is base64url-without-padding.
    alphabet = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
    assert all(c in alphabet for c in ref1)


def test_build_approval_resolution_ref_different_kind_or_id_differ():
    ref1 = build_approval_resolution_ref(approval_id="ap-1", approval_kind="exec")
    ref2 = build_approval_resolution_ref(approval_id="ap-1", approval_kind="plugin")
    ref3 = build_approval_resolution_ref(approval_id="ap-2", approval_kind="exec")
    assert ref1 != ref2
    assert ref1 != ref3


def test_build_approval_resolution_ref_rejects_non_canonical_kind():
    with pytest.raises(ValueError):
        build_approval_resolution_ref(approval_id="ap-1", approval_kind="user")
    with pytest.raises(ValueError):
        build_approval_resolution_ref(approval_id="", approval_kind="exec")


# ── ensure_operator_approval_resolution_refs ──────────────


def test_ensure_resolution_refs_noop_when_table_missing():
    conn = _fresh_db()
    try:
        ensure_operator_approval_resolution_refs(conn)  # no raise
    finally:
        conn.close()


def test_ensure_resolution_refs_adds_and_backfills():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE operator_approvals (
              approval_id TEXT NOT NULL,
              kind TEXT NOT NULL CHECK (kind IN ('exec', 'plugin', 'system-agent')),
              status TEXT,
              PRIMARY KEY (approval_id)
            ) STRICT;
            """
        )
        conn.execute(
            "INSERT INTO operator_approvals (approval_id, kind, status) "
            "VALUES ('a1', 'exec', 'pending'), ('a2', 'plugin', 'pending')"
        )
        conn.commit()
        ensure_operator_approval_resolution_refs(conn)
        rows = conn.execute("SELECT approval_id, resolution_ref FROM operator_approvals").fetchall()
        for row in rows:
            ref = row["resolution_ref"]
            assert ref is not None
            assert len(ref) == 43
            expected = build_approval_resolution_ref(
                approval_id=row["approval_id"],
                approval_kind=conn.execute(
                    "SELECT kind FROM operator_approvals WHERE approval_id = ?",
                    (row["approval_id"],),
                ).fetchone()["kind"],
            )
            assert ref == expected
    finally:
        conn.close()


def test_ensure_resolution_refs_creates_unique_index():
    conn = _fresh_db()
    try:
        conn.executescript(
            """
            CREATE TABLE operator_approvals (
              approval_id TEXT NOT NULL,
              kind TEXT NOT NULL CHECK (kind IN ('exec', 'plugin', 'system-agent')),
              status TEXT,
              PRIMARY KEY (approval_id)
            ) STRICT;
            """
        )
        conn.execute(
            "INSERT INTO operator_approvals (approval_id, kind, status) "
            "VALUES ('a1', 'exec', 'pending')"
        )
        conn.commit()
        ensure_operator_approval_resolution_refs(conn)
        # The unique index must exist after the call.
        idx = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name = 'idx_operator_approvals_resolution_ref'"
        ).fetchone()
        assert idx is not None
    finally:
        conn.close()


def test_ensure_resolution_refs_rejects_non_canonical_kind_row():
    conn = _fresh_db()
    try:
        # Bypass the CHECK constraint by inserting with a
        # canonical-shape CHECK that does not enforce kind.
        # We use the same CHECK as the canonical table; the
        # legacy kind sneaks in via raw SQL only when the
        # CHECK is loose. Here we just insert a row with
        # a kind that is_canonical_operator_approval_kind
        # rejects.
        conn.executescript(
            """
            CREATE TABLE operator_approvals (
              approval_id TEXT NOT NULL,
              kind TEXT,
              status TEXT,
              PRIMARY KEY (approval_id)
            );
            """
        )
        conn.execute(
            "INSERT INTO operator_approvals (approval_id, kind, status) "
            "VALUES ('a1', 'user', 'pending')"
        )
        conn.commit()
        with pytest.raises(RuntimeError, match="cannot be assigned a transport reference"):
            ensure_operator_approval_resolution_refs(conn)
    finally:
        conn.close()


def test_is_canonical_operator_approval_kind_smoke():
    # Re-exported check used by the resolution-ref helper.
    assert is_canonical_operator_approval_kind("system-agent") is True
    assert is_canonical_operator_approval_kind("user") is False
