"""Additive column + backfill ensure for the JARVIS state DB.

Mirrors OpenClaw's
``src/state/openclaw-state-db-schema-additive.ts`` 1:1.
The TS port is the home for the 100+ ``ensureColumn``
calls that grow every released table to the current
canonical column set without destructive operations.
Destructive or shape-changing repairs belong in doctor
(or the dedicated migration modules in this package).

The Python port keeps the same surface and uses the
``schema_helpers.ensure_column`` and
``legacy_backfills`` backfill helpers to apply the same
additive flow.

The caller owns the surrounding ``BEGIN IMMEDIATE``
transaction so every probe, DDL change, and backfill
observes one authoritative schema across processes.

Public surface:
- ``ensure_additive_state_columns(conn)`` — run the full
  additive ensure + backfill sequence
"""
from __future__ import annotations

import sqlite3

from .legacy_backfills import (
    _backfill_legacy_managed_image_roots,
    backfill_acp_replay_estimated_bytes,
    backfill_cron_jobs_from_job_json,
    backfill_cron_run_log_entry_json,
    backfill_delivery_queue_entries_from_entry_json,
    ensure_operator_approval_resolution_refs,
    migrate_legacy_cron_delivery_thread_ids,
    repair_legacy_task_agent_attribution,
    repair_legacy_task_delivery_statuses,
)
from .schema_helpers import ensure_column, table_exists


def ensure_additive_state_columns(conn: sqlite3.Connection) -> None:
    """Run every additive ``ensureColumn`` + matching backfill.

    Mirrors ``ensureAdditiveStateColumns`` from
    ``openclaw-state-db-schema-additive.ts``. The function
    is intentionally a single sequence of side-effecting
    calls — every column + every dependent backfill is
    paired exactly the way the TS source pairs them. The
    caller owns the surrounding ``BEGIN IMMEDIATE``
    transaction so the entire sequence rolls back together
    on any error.
    """
    # ── diagnostic_events ──────────────────────────────────
    added_diagnostic_event_sequence = ensure_column(
        conn,
        "diagnostic_events",
        "sequence INTEGER NOT NULL DEFAULT 0",
    )
    if added_diagnostic_event_sequence:
        # Preserve the legacy (created_at, rowid) order
        # before the new sequence index becomes
        # authoritative, including stable ties within each
        # scope.
        conn.executescript(
            """
            WITH ranked AS (
              SELECT
                rowid AS event_rowid,
                ROW_NUMBER() OVER (
                  PARTITION BY scope
                  ORDER BY created_at ASC, rowid ASC
                ) AS sequence
              FROM diagnostic_events
            )
            UPDATE diagnostic_events
            SET sequence = (
              SELECT ranked.sequence
              FROM ranked
              WHERE ranked.event_rowid = diagnostic_events.rowid
            );
            """
        )
    conn.execute("DROP INDEX IF EXISTS idx_diagnostic_events_scope_created;")

    # ── worktrees / node_host_config / apns_registrations ─
    ensure_column(conn, "worktrees", "provisioned_paths_json TEXT")
    ensure_column(conn, "node_host_config", "gateway_context_path TEXT")
    ensure_column(
        conn,
        "node_host_config",
        "installed_apps_sharing INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(conn, "apns_registrations", "relay_origin TEXT")

    # ── device_pairing_pending / paired ────────────────────
    ensure_column(conn, "device_pairing_pending", "refreshed_at_ms INTEGER")
    ensure_column(conn, "device_pairing_pending", "browser_origin TEXT")
    ensure_column(conn, "device_pairing_paired", "approved_via TEXT")
    ensure_column(conn, "device_pairing_paired", "browser_origin TEXT")
    ensure_column(conn, "device_pairing_paired", "operator_label TEXT")
    ensure_column(conn, "device_pairing_paired", "node_surface_json TEXT")
    ensure_column(
        conn, "device_pairing_paired", "pending_node_surface_json TEXT"
    )

    # ── cron_run_logs ──────────────────────────────────────
    ensure_column(conn, "cron_run_logs", "status TEXT")
    ensure_column(conn, "cron_run_logs", "error TEXT")
    ensure_column(conn, "cron_run_logs", "summary TEXT")
    ensure_column(conn, "cron_run_logs", "diagnostics_summary TEXT")
    ensure_column(conn, "cron_run_logs", "delivery_status TEXT")
    ensure_column(conn, "cron_run_logs", "delivery_error TEXT")
    ensure_column(conn, "cron_run_logs", "delivered INTEGER")
    ensure_column(conn, "cron_run_logs", "session_id TEXT")
    ensure_column(conn, "cron_run_logs", "session_key TEXT")
    ensure_column(conn, "cron_run_logs", "run_id TEXT")
    ensure_column(conn, "cron_run_logs", "run_at_ms INTEGER")
    ensure_column(conn, "cron_run_logs", "duration_ms INTEGER")
    ensure_column(conn, "cron_run_logs", "next_run_at_ms INTEGER")
    ensure_column(conn, "cron_run_logs", "model TEXT")
    ensure_column(conn, "cron_run_logs", "provider TEXT")
    ensure_column(conn, "cron_run_logs", "total_tokens INTEGER")
    ensure_column(
        conn, "cron_run_logs", "entry_json TEXT NOT NULL DEFAULT '{}'"
    )
    ensure_column(
        conn, "cron_run_logs", "created_at INTEGER NOT NULL DEFAULT 0"
    )
    backfill_cron_run_log_entry_json(conn)

    # ── acp_replay_events / sessions ───────────────────────
    ensure_column(
        conn,
        "acp_replay_events",
        "estimated_bytes INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(
        conn,
        "acp_replay_sessions",
        "estimated_bytes INTEGER NOT NULL DEFAULT 0",
    )
    backfill_acp_replay_estimated_bytes(conn)

    # ── cron_jobs (the big one) ────────────────────────────
    ensure_column(conn, "cron_jobs", "description TEXT")
    ensure_column(conn, "cron_jobs", "declaration_key TEXT")
    ensure_column(conn, "cron_jobs", "display_name TEXT")
    ensure_column(conn, "cron_jobs", "owner_agent_id TEXT")
    ensure_column(conn, "cron_jobs", "owner_session_key TEXT")
    ensure_column(conn, "cron_jobs", "name TEXT NOT NULL DEFAULT ''")
    ensure_column(conn, "cron_jobs", "enabled INTEGER NOT NULL DEFAULT 1")
    ensure_column(conn, "cron_jobs", "delete_after_run INTEGER")
    ensure_column(
        conn, "cron_jobs", "created_at_ms INTEGER NOT NULL DEFAULT 0"
    )
    ensure_column(conn, "cron_jobs", "agent_id TEXT")
    ensure_column(conn, "cron_jobs", "session_key TEXT")
    ensure_column(
        conn,
        "cron_jobs",
        "schedule_kind TEXT NOT NULL DEFAULT 'manual'",
    )
    ensure_column(conn, "cron_jobs", "schedule_expr TEXT")
    ensure_column(conn, "cron_jobs", "schedule_tz TEXT")
    ensure_column(conn, "cron_jobs", "every_ms INTEGER")
    ensure_column(conn, "cron_jobs", "anchor_ms INTEGER")
    ensure_column(conn, "cron_jobs", "at TEXT")
    ensure_column(conn, "cron_jobs", "stagger_ms INTEGER")
    ensure_column(
        conn,
        "cron_jobs",
        "session_target TEXT NOT NULL DEFAULT 'main'",
    )
    ensure_column(
        conn, "cron_jobs", "wake_mode TEXT NOT NULL DEFAULT 'auto'"
    )
    ensure_column(conn, "cron_jobs", "trigger_script TEXT")
    ensure_column(conn, "cron_jobs", "trigger_once INTEGER")
    ensure_column(
        conn,
        "cron_jobs",
        "payload_kind TEXT NOT NULL DEFAULT 'message'",
    )
    ensure_column(conn, "cron_jobs", "payload_message TEXT")
    ensure_column(conn, "cron_jobs", "payload_model TEXT")
    ensure_column(conn, "cron_jobs", "payload_fallbacks_json TEXT")
    ensure_column(conn, "cron_jobs", "payload_thinking TEXT")
    ensure_column(conn, "cron_jobs", "payload_timeout_seconds INTEGER")
    ensure_column(
        conn, "cron_jobs", "payload_allow_unsafe_external_content INTEGER"
    )
    ensure_column(
        conn, "cron_jobs", "payload_external_content_source_json TEXT"
    )
    ensure_column(conn, "cron_jobs", "payload_light_context INTEGER")
    ensure_column(conn, "cron_jobs", "payload_tools_allow_json TEXT")
    ensure_column(
        conn, "cron_jobs", "payload_tools_allow_is_default INTEGER"
    )
    ensure_column(conn, "cron_jobs", "delivery_mode TEXT")
    ensure_column(conn, "cron_jobs", "delivery_channel TEXT")
    ensure_column(conn, "cron_jobs", "delivery_to TEXT")
    ensure_column(conn, "cron_jobs", "delivery_thread_id TEXT")
    ensure_column(conn, "cron_jobs", "delivery_account_id TEXT")
    ensure_column(conn, "cron_jobs", "delivery_best_effort INTEGER")
    ensure_column(conn, "cron_jobs", "delivery_completion_mode TEXT")
    ensure_column(conn, "cron_jobs", "delivery_completion_to TEXT")
    ensure_column(conn, "cron_jobs", "failure_delivery_mode TEXT")
    ensure_column(conn, "cron_jobs", "failure_delivery_channel TEXT")
    ensure_column(conn, "cron_jobs", "failure_delivery_to TEXT")
    ensure_column(
        conn, "cron_jobs", "failure_delivery_account_id TEXT"
    )
    ensure_column(conn, "cron_jobs", "failure_alert_disabled INTEGER")
    ensure_column(conn, "cron_jobs", "failure_alert_after INTEGER")
    ensure_column(conn, "cron_jobs", "failure_alert_channel TEXT")
    ensure_column(conn, "cron_jobs", "failure_alert_to TEXT")
    ensure_column(
        conn, "cron_jobs", "failure_alert_cooldown_ms INTEGER"
    )
    ensure_column(
        conn, "cron_jobs", "failure_alert_include_skipped INTEGER"
    )
    ensure_column(conn, "cron_jobs", "failure_alert_mode TEXT")
    ensure_column(
        conn, "cron_jobs", "failure_alert_account_id TEXT"
    )
    ensure_column(conn, "cron_jobs", "next_run_at_ms INTEGER")
    ensure_column(conn, "cron_jobs", "running_at_ms INTEGER")
    ensure_column(conn, "cron_jobs", "last_run_at_ms INTEGER")
    ensure_column(conn, "cron_jobs", "last_run_status TEXT")
    ensure_column(conn, "cron_jobs", "last_error TEXT")
    ensure_column(conn, "cron_jobs", "last_duration_ms INTEGER")
    ensure_column(conn, "cron_jobs", "consecutive_errors INTEGER")
    ensure_column(conn, "cron_jobs", "consecutive_skipped INTEGER")
    ensure_column(conn, "cron_jobs", "schedule_error_count INTEGER")
    ensure_column(conn, "cron_jobs", "last_delivery_status TEXT")
    ensure_column(conn, "cron_jobs", "last_delivery_error TEXT")
    ensure_column(conn, "cron_jobs", "last_delivered INTEGER")
    ensure_column(
        conn, "cron_jobs", "last_failure_alert_at_ms INTEGER"
    )
    ensure_column(
        conn, "cron_jobs", "state_json TEXT NOT NULL DEFAULT '{}'"
    )
    ensure_column(conn, "cron_jobs", "runtime_updated_at_ms INTEGER")
    ensure_column(conn, "cron_jobs", "schedule_identity TEXT")
    ensure_column(conn, "cron_jobs", "sort_order INTEGER NOT NULL DEFAULT 0")
    backfill_cron_jobs_from_job_json(conn)
    added_delivery_thread_id_type = ensure_column(
        conn, "cron_jobs", "delivery_thread_id_type TEXT"
    )
    if added_delivery_thread_id_type:
        migrate_legacy_cron_delivery_thread_ids(conn)

    # ── sandbox_registry_entries ───────────────────────────
    ensure_column(conn, "sandbox_registry_entries", "session_key TEXT")
    ensure_column(conn, "sandbox_registry_entries", "backend_id TEXT")
    ensure_column(conn, "sandbox_registry_entries", "runtime_label TEXT")
    ensure_column(conn, "sandbox_registry_entries", "image TEXT")
    ensure_column(
        conn, "sandbox_registry_entries", "created_at_ms INTEGER"
    )
    ensure_column(
        conn, "sandbox_registry_entries", "last_used_at_ms INTEGER"
    )
    ensure_column(
        conn, "sandbox_registry_entries", "config_label_kind TEXT"
    )
    ensure_column(conn, "sandbox_registry_entries", "config_hash TEXT")
    ensure_column(conn, "sandbox_registry_entries", "cdp_port INTEGER")
    ensure_column(
        conn, "sandbox_registry_entries", "no_vnc_port INTEGER"
    )

    # ── delivery_queue_entries ─────────────────────────────
    ensure_column(conn, "delivery_queue_entries", "entry_kind TEXT")
    ensure_column(conn, "delivery_queue_entries", "session_key TEXT")
    ensure_column(conn, "delivery_queue_entries", "channel TEXT")
    ensure_column(conn, "delivery_queue_entries", "target TEXT")
    ensure_column(conn, "delivery_queue_entries", "account_id TEXT")
    ensure_column(
        conn, "delivery_queue_entries", "retry_count INTEGER NOT NULL DEFAULT 0"
    )
    ensure_column(conn, "delivery_queue_entries", "last_attempt_at INTEGER")
    ensure_column(conn, "delivery_queue_entries", "last_error TEXT")
    ensure_column(conn, "delivery_queue_entries", "recovery_state TEXT")
    ensure_column(
        conn, "delivery_queue_entries", "platform_send_started_at INTEGER"
    )
    backfill_delivery_queue_entries_from_entry_json(conn)

    # ── commitments ────────────────────────────────────────
    ensure_column(conn, "commitments", "account_id TEXT")
    ensure_column(conn, "commitments", "recipient_id TEXT")
    ensure_column(conn, "commitments", "thread_id TEXT")
    ensure_column(conn, "commitments", "sender_id TEXT")
    ensure_column(
        conn, "commitments", "kind TEXT NOT NULL DEFAULT 'followup'"
    )
    ensure_column(
        conn,
        "commitments",
        "sensitivity TEXT NOT NULL DEFAULT 'normal'",
    )
    ensure_column(
        conn, "commitments", "source TEXT NOT NULL DEFAULT 'unknown'"
    )
    ensure_column(conn, "commitments", "reason TEXT NOT NULL DEFAULT ''")
    ensure_column(
        conn, "commitments", "suggested_text TEXT NOT NULL DEFAULT ''"
    )
    ensure_column(
        conn, "commitments", "dedupe_key TEXT NOT NULL DEFAULT ''"
    )
    ensure_column(
        conn, "commitments", "confidence REAL NOT NULL DEFAULT 0"
    )
    ensure_column(
        conn, "commitments", "due_timezone TEXT NOT NULL DEFAULT 'UTC'"
    )
    ensure_column(conn, "commitments", "source_message_id TEXT")
    ensure_column(conn, "commitments", "source_run_id TEXT")
    ensure_column(
        conn, "commitments", "created_at_ms INTEGER NOT NULL DEFAULT 0"
    )
    ensure_column(
        conn, "commitments", "attempts INTEGER NOT NULL DEFAULT 0"
    )
    ensure_column(conn, "commitments", "last_attempt_at_ms INTEGER")
    ensure_column(conn, "commitments", "sent_at_ms INTEGER")
    ensure_column(conn, "commitments", "dismissed_at_ms INTEGER")
    ensure_column(conn, "commitments", "snoozed_until_ms INTEGER")
    ensure_column(conn, "commitments", "expired_at_ms INTEGER")

    # ── managed_outgoing_image_records ────────────────────
    # The shipped JSON runtime predeclared this table but
    # never populated it. The transitional default makes
    # ``ADD COLUMN`` portable; schema-v2 tables are
    # rebuilt from canonical STRICT SQL immediately
    # afterward, removing it.
    added_original_media_root = ensure_column(
        conn,
        "managed_outgoing_image_records",
        "original_media_root TEXT NOT NULL DEFAULT ''",
    )
    if added_original_media_root:
        _backfill_legacy_managed_image_roots(conn)
    ensure_column(conn, "managed_outgoing_image_records", "agent_id TEXT")
    ensure_column(
        conn,
        "managed_outgoing_image_records",
        "cleanup_pending INTEGER NOT NULL DEFAULT 0 CHECK (cleanup_pending IN (0, 1))",
    )

    # ── current_conversation_bindings ─────────────────────
    ensure_column(
        conn,
        "current_conversation_bindings",
        "target_agent_id TEXT NOT NULL DEFAULT 'main'",
    )
    ensure_column(
        conn, "current_conversation_bindings", "target_session_id TEXT"
    )
    ensure_column(
        conn,
        "current_conversation_bindings",
        "conversation_kind TEXT NOT NULL DEFAULT 'channel'",
    )

    # ── device_bootstrap_tokens / gateway_restart_* ────────
    ensure_column(
        conn, "device_bootstrap_tokens", "pending_profile_json TEXT"
    )
    ensure_column(
        conn,
        "gateway_restart_handoff",
        "restart_trace_started_at INTEGER",
    )
    ensure_column(
        conn, "gateway_restart_handoff", "restart_trace_last_at INTEGER"
    )
    ensure_column(conn, "gateway_restart_intent", "reason TEXT")
    ensure_column(conn, "gateway_restart_sentinel", "delivery_channel TEXT")
    ensure_column(conn, "gateway_restart_sentinel", "delivery_to TEXT")
    ensure_column(
        conn, "gateway_restart_sentinel", "delivery_account_id TEXT"
    )
    ensure_column(conn, "gateway_restart_sentinel", "message TEXT")
    ensure_column(
        conn, "gateway_restart_sentinel", "continuation_json TEXT"
    )
    ensure_column(conn, "gateway_restart_sentinel", "doctor_hint TEXT")
    ensure_column(conn, "gateway_restart_sentinel", "stats_json TEXT")
    ensure_column(conn, "gateway_boot_lifecycle", "startup_reason TEXT")

    # ── official_external_plugin_catalog_snapshots ────────
    ensure_column(
        conn,
        "official_external_plugin_catalog_snapshots",
        "trust_mode TEXT",
    )
    ensure_column(
        conn,
        "official_external_plugin_catalog_snapshots",
        "trust_key_id TEXT",
    )
    ensure_column(
        conn,
        "official_external_plugin_catalog_snapshots",
        "trust_signature_count INTEGER",
    )
    ensure_column(
        conn,
        "official_external_plugin_catalog_snapshots",
        "trust_threshold INTEGER",
    )
    ensure_column(
        conn,
        "official_external_plugin_catalog_snapshots",
        "trust_verified_at TEXT",
    )

    # ── task_runs / subagent_runs ──────────────────────────
    added_task_requester_agent_id = ensure_column(
        conn, "task_runs", "requester_agent_id TEXT"
    )
    if added_task_requester_agent_id:
        repair_legacy_task_agent_attribution(conn)
    repair_legacy_task_delivery_statuses(conn)
    ensure_column(conn, "task_runs", "tool_use_count INTEGER")
    ensure_column(conn, "task_runs", "last_tool_name TEXT")
    ensure_column(conn, "task_runs", "detail_json TEXT")
    ensure_column(conn, "subagent_runs", "task_name TEXT")
    ensure_column(
        conn, "subagent_runs", "requester_settle_wake_status TEXT"
    )
    ensure_column(
        conn, "subagent_runs", "requester_settle_wake_attempt_count INTEGER"
    )
    ensure_column(
        conn, "subagent_runs", "requester_settle_wake_replay_count INTEGER"
    )
    ensure_column(
        conn,
        "subagent_runs",
        "requester_settle_wake_next_attempt_at INTEGER",
    )
    ensure_column(
        conn,
        "subagent_runs",
        "requester_settle_wake_batch_run_ids_json TEXT",
    )
    ensure_column(
        conn, "subagent_runs", "requester_settle_wake_last_error TEXT"
    )
    ensure_column(
        conn, "subagent_runs", "requester_settle_wake_retire_after INTEGER"
    )
    ensure_column(conn, "subagent_runs", "swarm_group_id TEXT")
    ensure_column(conn, "subagent_runs", "swarm_collector INTEGER")
    ensure_column(
        conn, "subagent_runs", "swarm_output_schema_json TEXT"
    )
    ensure_column(conn, "subagent_runs", "swarm_completion_status TEXT")
    ensure_column(conn, "subagent_runs", "swarm_structured_json TEXT")
    ensure_column(conn, "subagent_runs", "swarm_schema_error TEXT")
    ensure_column(conn, "subagent_runs", "swarm_usage_json TEXT")

    # ── worker_environments / worker_workspace_* ──────────
    ensure_column(
        conn, "worker_environments", "bootstrap_bundle_hash TEXT"
    )
    ensure_column(
        conn, "worker_environments", "bootstrap_openclaw_version TEXT"
    )
    ensure_column(
        conn,
        "worker_environments",
        "bootstrap_protocol_features_json TEXT",
    )
    ensure_column(
        conn,
        "worker_environments",
        "owner_epoch INTEGER NOT NULL DEFAULT 0 CHECK (owner_epoch >= 0)",
    )
    ensure_column(conn, "worker_environments", "ssh_host_key TEXT")
    ensure_column(
        conn, "worker_workspace_pending_results", "staged_result_ref TEXT"
    )
    ensure_column(
        conn,
        "worker_environments",
        "teardown_terminal_state TEXT CHECK (teardown_terminal_state IN ('destroyed', 'failed'))",
    )

    # ── operator_approvals (resolution-ref namespace) ─────
    ensure_operator_approval_resolution_refs(conn)


__all__ = ["ensure_additive_state_columns"]
