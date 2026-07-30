"""Legacy backfills + projection repairs for the JARVIS state DB.

Mirrors OpenClaw's
``src/state/openclaw-state-db-legacy-backfills.ts`` 1:1.
The TS port is the home for the row-level projections that
read from JSON blob payloads (``entry_json`` /
``job_json`` / ``record_json``) and project them into
queryable columns, plus the operator-approval
``resolution_ref`` namespace and the legacy
``task_runs`` repair paths.

The Python port keeps the same surface and uses raw
``sqlite3`` (the TS port uses Kysely for typed query
bodies). All functions are defensive: they check the
table + required columns exist and return early when the
shape is not the one they can repair.

Why these are here: the caller owns the
``state.schema.ensure`` transaction, so every probe, DDL
change, and backfill observes one authoritative schema
across processes. Mixing backfills into a runtime
"ensure_schema" call would let a partial state leak into
runtime reads.

Public surface:
- ``backfill_acp_replay_estimated_bytes(conn)``
- ``backfill_cron_run_log_entry_json(conn)``
- ``migrate_legacy_cron_delivery_thread_ids(conn)``
- ``repair_legacy_task_agent_attribution(conn)``
- ``repair_legacy_task_delivery_statuses(conn)``
- ``backfill_cron_jobs_from_job_json(conn)``
- ``backfill_delivery_queue_entries_from_entry_json(conn)``
- ``ensure_operator_approval_resolution_refs(conn)``
- ``build_approval_resolution_ref(approval_id, approval_kind)``
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from typing import Any, Optional

from .operator_approval_migration import is_canonical_operator_approval_kind
from .schema_helpers import ensure_column, table_exists, table_has_column


# ── JSON record helpers (Python adaptation) ──────────────
#
# The TS port uses ``isRecord`` from
# ``@openclaw/normalization-core/record-coerce`` to parse
# JSON payloads defensively. The Python port keeps the
# same shape via a tiny inline helper.


def _parse_json_record(value: Any) -> Optional[dict[str, Any]]:
    """Parse ``value`` as a JSON object record.

    Mirrors ``parseJsonRecord`` from
    ``openclaw-state-db-legacy-backfills.ts``. Returns
    ``None`` for non-strings, non-objects, arrays, and
    JSON parse errors.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _text_field(record: Optional[dict[str, Any]], key: str) -> Optional[str]:
    """Return ``record[key]`` when it's a non-empty string."""
    if not record:
        return None
    value = record.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _number_field(record: Optional[dict[str, Any]], key: str) -> Optional[float]:
    """Return ``record[key]`` when it's a finite number."""
    if not record:
        return None
    value = record.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _record_field(record: Optional[dict[str, Any]], key: str) -> Optional[dict[str, Any]]:
    """Return ``record[key]`` when it's a non-array object."""
    if not record:
        return None
    value = record.get(key)
    if isinstance(value, dict) and not isinstance(value, list):
        return value
    return None


def _json_field(value: Any) -> Optional[str]:
    """JSON-encode ``value`` (mirrors OpenClaw's ``jsonField``).

    The TS port encodes ``undefined`` as ``null``; the
    Python port encodes ``None`` as JSON ``null`` too.
    """
    if value is None:
        return None
    return json.dumps(value)


def _boolean_field(record: Optional[dict[str, Any]], key: str) -> Optional[int]:
    """Return ``record[key]`` as 0/1 when it's a bool, else ``None``."""
    if not record:
        return None
    value = record.get(key)
    if isinstance(value, bool):
        return 1 if value else 0
    return None


def _cron_session_target_field(record: dict[str, Any]) -> Optional[str]:
    """Validate ``sessionTarget`` against the closed cron set.

    Mirrors ``cronSessionTargetField``.
    """
    value = _text_field(record, "sessionTarget")
    if not value:
        return None
    if value in ("main", "isolated", "current") or value.startswith("session:"):
        return value
    return None


def _cron_wake_mode_field(record: dict[str, Any]) -> Optional[str]:
    """Validate ``wakeMode`` against the closed cron set.

    Mirrors ``cronWakeModeField``.
    """
    value = _text_field(record, "wakeMode")
    return value if value in ("now", "next-heartbeat") else None


def _failure_destination_field(
    record: Optional[dict[str, Any]],
    key: str,
) -> Optional[str]:
    """Return the failure-destination field as an empty string for null, or null when missing.

    Mirrors ``failureDestinationField``. Returns ``""``
    when the record has the key but the value isn't a
    non-empty string (the legacy projection stores
    "cleared" as the empty string so a downstream filter
    can distinguish "set to empty" from "never set").
    Returns ``None`` when the key is absent.
    """
    if not record or key not in record:
        return None
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return ""


# ── backfillAcpReplayEstimatedBytes ────────────────────────


def backfill_acp_replay_estimated_bytes(conn: sqlite3.Connection) -> None:
    """Backfill ``acp_replay_*`` ``estimated_bytes`` columns.

    Mirrors ``backfillAcpReplayEstimatedBytes``. Skips
    when the tables / columns are missing; recomputes
    only the rows that still hold the default 0.
    """
    if not table_exists(conn, "acp_replay_events") or not table_has_column(
        conn, "acp_replay_events", "estimated_bytes"
    ):
        return
    pending_event = conn.execute(
        "SELECT 1 FROM acp_replay_events WHERE estimated_bytes = 0 LIMIT 1"
    ).fetchone()
    pending_session = conn.execute(
        "SELECT 1 FROM acp_replay_sessions WHERE estimated_bytes = 0 LIMIT 1"
    ).fetchone()
    if not pending_event and not pending_session:
        return
    conn.executescript(
        """
        UPDATE acp_replay_events
           SET estimated_bytes = length(session_id) + length(session_key)
                                + length(update_json)
                                + COALESCE(length(run_id), 0) + 32
         WHERE estimated_bytes = 0;
        UPDATE acp_replay_sessions
           SET estimated_bytes = length(session_id) + length(session_key)
                                + length(cwd) + 32
                                + COALESCE((SELECT SUM(e.estimated_bytes)
                                              FROM acp_replay_events e
                                             WHERE e.session_id = acp_replay_sessions.session_id), 0)
         WHERE estimated_bytes = 0;
        """
    )


# ── backfillCronRunLogEntryJson ────────────────────────────


def backfill_cron_run_log_entry_json(conn: sqlite3.Connection) -> None:
    """Project ``cron_run_logs`` legacy columns into ``entry_json``.

    Mirrors ``backfillCronRunLogEntryJson``. Runs only for
    rows that still hold the ``entry_json = '{}'`` default
    and the source ``ts`` / ``job_id`` columns exist.
    """
    if not table_exists(conn, "cron_run_logs") or not table_has_column(
        conn, "cron_run_logs", "entry_json"
    ):
        return
    # The legacy source columns must all exist for the
    # projection to run; a partial-shape table can't
    # produce a meaningful ``entry_json``.
    required = ("store_key", "job_id", "seq", "ts")
    if not all(
        table_has_column(conn, "cron_run_logs", column) for column in required
    ):
        return
    rows = conn.execute(
        "SELECT store_key, job_id, seq, ts "
        "FROM cron_run_logs "
        "WHERE entry_json = '{}'"
    ).fetchall()
    if not rows:
        return
    update = conn.cursor()
    for row in rows:
        store_key, job_id, seq, ts = row[0], row[1], row[2], row[3]
        payload = json.dumps(
            {"ts": int(ts), "jobId": job_id, "action": "finished"}
        )
        update.execute(
            "UPDATE cron_run_logs SET entry_json = ? "
            "WHERE store_key = ? AND job_id = ? AND seq = ?",
            (payload, store_key, job_id, seq),
        )


# ── migrateLegacyCronDeliveryThreadIds ─────────────────────


def migrate_legacy_cron_delivery_thread_ids(conn: sqlite3.Connection) -> None:
    """Repair the ``delivery_thread_id_type`` column for legacy rows.

    Mirrors ``migrateLegacyCronDeliveryThreadIds``. The
    first normalized cron migration could not project
    numeric thread IDs; this backfill recovers that lost
    shape from ``job_json.delivery.threadId``.
    """
    if not table_exists(conn, "cron_jobs"):
        return
    required = (
        "store_key",
        "job_id",
        "job_json",
        "delivery_thread_id",
        "delivery_thread_id_type",
    )
    if not all(
        table_has_column(conn, "cron_jobs", column) for column in required
    ):
        return
    rows = conn.execute(
        "SELECT store_key, job_id, job_json, delivery_thread_id "
        "FROM cron_jobs "
        "WHERE delivery_thread_id_type IS NULL"
    ).fetchall()
    if not rows:
        return
    update = conn.cursor()
    for row in rows:
        store_key, job_id, job_json, delivery_thread_id = (
            row[0],
            row[1],
            row[2],
            row[3],
        )
        job = _parse_json_record(job_json)
        delivery = _record_field(job, "delivery") if job else None
        typed = delivery.get("threadId") if delivery else None
        if delivery_thread_id is None:
            # Recover only the known lost shape (numeric thread ID).
            if isinstance(typed, (int, float)) and not isinstance(typed, bool):
                update.execute(
                    "UPDATE cron_jobs "
                    "SET delivery_thread_id = ?, delivery_thread_id_type = ? "
                    "WHERE store_key = ? AND job_id = ? AND delivery_thread_id_type IS NULL",
                    (str(int(typed)), "number", store_key, job_id),
                )
            continue
        # delivery_thread_id is a string; tag as number when
        # the source matched numeric and matches the string.
        if (
            isinstance(typed, (int, float))
            and not isinstance(typed, bool)
            and str(int(typed)) == delivery_thread_id
        ):
            type_label = "number"
        else:
            type_label = "string"
        update.execute(
            "UPDATE cron_jobs "
            "SET delivery_thread_id = ?, delivery_thread_id_type = ? "
            "WHERE store_key = ? AND job_id = ? AND delivery_thread_id_type IS NULL",
            (delivery_thread_id, type_label, store_key, job_id),
        )


# ── repairLegacyTaskAgentAttribution ───────────────────────


def repair_legacy_task_agent_attribution(conn: sqlite3.Connection) -> None:
    """Repair ``task_runs.requester_agent_id`` from legacy key shapes.

    Mirrors ``repairLegacyTaskAgentAttribution``. Before
    ``requester_agent_id`` existed, scoped subagent/ACP
    rows stored the requester in ``agent_id``. Repair only
    rows with recoverable requester provenance; global
    legacy rows keep the existing fallback behavior.
    """
    if not table_exists(conn, "task_runs") or not table_has_column(
        conn, "task_runs", "requester_agent_id"
    ):
        return
    # The full repair reads ``owner_key`` /
    # ``requester_session_key`` / ``child_session_key`` /
    # ``runtime`` / ``agent_id``. A partial-shape table
    # can't run the projection; skip when any required
    # column is missing.
    required_columns = (
        "requester_agent_id",
        "owner_key",
        "requester_session_key",
        "child_session_key",
        "runtime",
        "agent_id",
    )
    if not all(
        table_has_column(conn, "task_runs", column)
        for column in required_columns
    ):
        return
    conn.executescript(
        """
        UPDATE task_runs
        SET
          requester_agent_id = CASE
            WHEN owner_key GLOB 'agent:*:*' THEN substr(
              owner_key,
              7,
              instr(substr(owner_key, 7), ':') - 1
            )
            WHEN requester_session_key GLOB 'agent:*:*' THEN substr(
              requester_session_key,
              7,
              instr(substr(requester_session_key, 7), ':') - 1
            )
            WHEN agent_id <> substr(
              child_session_key,
              7,
              instr(substr(child_session_key, 7), ':') - 1
            ) THEN agent_id
            ELSE NULL
          END,
          agent_id = substr(
            child_session_key,
            7,
            instr(substr(child_session_key, 7), ':') - 1
          )
        WHERE requester_agent_id IS NULL
          AND runtime IN ('subagent', 'acp')
          AND child_session_key GLOB 'agent:*:*'
          AND instr(substr(child_session_key, 7), ':') > 1
          AND (
            owner_key GLOB 'agent:*:*'
            OR requester_session_key GLOB 'agent:*:*'
            OR (
              agent_id IS NOT NULL
              AND agent_id <> substr(
                child_session_key,
                7,
                instr(substr(child_session_key, 7), ':') - 1
              )
            )
          );
        """
    )


# ── repairLegacyTaskDeliveryStatuses ──────────────────────


def repair_legacy_task_delivery_statuses(conn: sqlite3.Connection) -> None:
    """Canonicalize the ``task_runs.delivery_status`` enum.

    Mirrors ``repairLegacyTaskDeliveryStatuses``.
    Successful sidecar imports archive their source, so
    database open must also canonicalize rows already
    copied by released migrations.
    """
    if not table_exists(conn, "task_runs") or not table_has_column(
        conn, "task_runs", "delivery_status"
    ):
        return
    conn.executescript(
        "UPDATE task_runs SET delivery_status = 'not_applicable' "
        "WHERE delivery_status = 'not-requested';"
    )


# ── backfillCronJobsFromJobJson ───────────────────────────


def backfill_cron_jobs_from_job_json(conn: sqlite3.Connection) -> None:
    """Project legacy ``cron_jobs.job_json`` into canonical columns.

    Mirrors ``backfillCronJobsFromJobJson``. Only runs on
    rows that still hold the legacy defaults
    (``schedule_kind = 'manual'`` or
    ``payload_kind = 'message'`` or ``name = ''``). The
    ``job_json`` blob remains the source of truth; the
    columns are a queryable projection.
    """
    if (
        not table_exists(conn, "cron_jobs")
        or not table_has_column(conn, "cron_jobs", "job_json")
        or not table_has_column(conn, "cron_jobs", "schedule_kind")
        or not table_has_column(conn, "cron_jobs", "payload_kind")
    ):
        return
    # The full UPDATE references every column in the
    # canonical cron_jobs shape; a partial-shape table
    # can't run the projection. The OpenClaw source runs
    # the full statement unconditionally, but JARVIS may
    # have a v0 cron_jobs table that's still being grown;
    # skipping is safer than a partial-write.
    required = (
        "store_key",
        "job_id",
        "job_json",
        "updated_at",
        "name",
        "enabled",
        "delete_after_run",
        "created_at_ms",
        "agent_id",
        "session_key",
        "schedule_kind",
        "schedule_expr",
        "schedule_tz",
        "every_ms",
        "anchor_ms",
        "at",
        "stagger_ms",
        "session_target",
        "wake_mode",
        "payload_kind",
        "payload_message",
        "payload_model",
        "payload_fallbacks_json",
        "payload_thinking",
        "payload_timeout_seconds",
        "payload_allow_unsafe_external_content",
        "payload_external_content_source_json",
        "payload_light_context",
        "payload_tools_allow_json",
        "delivery_mode",
        "delivery_channel",
        "delivery_to",
        "delivery_thread_id",
        "delivery_account_id",
        "delivery_best_effort",
        "delivery_completion_mode",
        "delivery_completion_to",
        "failure_delivery_mode",
        "failure_delivery_channel",
        "failure_delivery_to",
        "failure_delivery_account_id",
        "failure_alert_disabled",
        "failure_alert_after",
        "failure_alert_channel",
        "failure_alert_to",
        "failure_alert_cooldown_ms",
        "failure_alert_include_skipped",
        "failure_alert_mode",
        "failure_alert_account_id",
        "runtime_updated_at_ms",
    )
    if not all(
        table_has_column(conn, "cron_jobs", column) for column in required
    ):
        return
    rows = conn.execute(
        "SELECT store_key, job_id, job_json, updated_at "
        "FROM cron_jobs "
        "WHERE schedule_kind = 'manual' OR payload_kind = 'message' OR name = ''"
    ).fetchall()
    if not rows:
        return
    update = conn.cursor()
    for row in rows:
        store_key, job_id, job_json, updated_at = (
            row[0],
            row[1],
            row[2],
            row[3],
        )
        job = _parse_json_record(job_json)
        if not job:
            continue
        schedule = _record_field(job, "schedule")
        payload = _record_field(job, "payload")
        if not schedule or not payload:
            continue
        schedule_kind = _text_field(schedule, "kind")
        payload_kind = _text_field(payload, "kind")
        is_at = schedule_kind == "at" and _text_field(schedule, "at")
        is_every = (
            schedule_kind == "every" and _number_field(schedule, "everyMs") is not None
        )
        is_cron = schedule_kind == "cron" and _text_field(schedule, "expr")
        is_system_event = (
            payload_kind == "systemEvent" and _text_field(payload, "text")
        )
        is_agent_turn = (
            payload_kind == "agentTurn" and _text_field(payload, "message")
        )
        if not (is_at or is_every or is_cron) or not (
            is_system_event or is_agent_turn
        ):
            continue
        fallback_time = int(updated_at) if updated_at is not None else 0
        delivery = _record_field(job, "delivery")
        completion_destination = (
            _record_field(delivery, "completionDestination") if delivery else None
        )
        failure_destination = (
            _record_field(delivery, "failureDestination") if delivery else None
        )
        failure_alert_value = job.get("failureAlert")
        failure_alert = (
            failure_alert_value
            if isinstance(failure_alert_value, dict) and not isinstance(failure_alert_value, list)
            else None
        )
        if failure_alert is None and failure_alert_value is False:
            failure_alert_disabled = 1
        elif failure_alert is not None:
            failure_alert_disabled = 0
        else:
            failure_alert_disabled = None
        session_target = _cron_session_target_field(job) or (
            "isolated" if payload_kind == "agentTurn" else "main"
        )
        wake_mode = _cron_wake_mode_field(job) or "now"
        run_id_str = _text_field(job, "name") or job_id
        enabled_int = 0 if job.get("enabled") is False else 1
        delete_after_run = _boolean_field(job, "deleteAfterRun")
        created_at_ms = _number_field(job, "createdAtMs")
        created_at_ms = int(created_at_ms) if created_at_ms is not None else fallback_time
        agent_id_val = _text_field(job, "agentId")
        session_key_val = _text_field(job, "sessionKey")
        schedule_expr = (
            _text_field(schedule, "expr") if (schedule_kind == "cron") else None
        )
        schedule_tz = (
            _text_field(schedule, "tz") if (schedule_kind == "cron") else None
        )
        every_ms = (
            _number_field(schedule, "everyMs")
            if (schedule_kind == "every")
            else None
        )
        anchor_ms = (
            _number_field(schedule, "anchorMs")
            if (schedule_kind == "every")
            else None
        )
        at_val = (
            _text_field(schedule, "at") if (schedule_kind == "at") else None
        )
        stagger_ms = (
            _number_field(schedule, "staggerMs")
            if (schedule_kind == "cron")
            else None
        )
        payload_message = (
            _text_field(payload, "text")
            if (payload_kind == "systemEvent")
            else _text_field(payload, "message")
        )
        payload_model = (
            _text_field(payload, "model") if (payload_kind == "agentTurn") else None
        )
        payload_fallbacks = (
            _json_field(payload.get("fallbacks"))
            if (payload_kind == "agentTurn")
            else None
        )
        payload_thinking = (
            _text_field(payload, "thinking")
            if (payload_kind == "agentTurn")
            else None
        )
        payload_timeout_seconds = (
            _number_field(payload, "timeoutSeconds")
            if (payload_kind == "agentTurn")
            else None
        )
        allow_unsafe_val = payload.get("allowUnsafeExternalContent")
        payload_allow_unsafe = (
            1
            if (payload_kind == "agentTurn" and allow_unsafe_val is True)
            else 0
            if (payload_kind == "agentTurn" and allow_unsafe_val is False)
            else None
        )
        payload_external_content_source = (
            _json_field(payload.get("externalContentSource"))
            if (payload_kind == "agentTurn")
            else None
        )
        light_context_val = payload.get("lightContext")
        payload_light_context = (
            1
            if (payload_kind == "agentTurn" and light_context_val is True)
            else 0
            if (payload_kind == "agentTurn" and light_context_val is False)
            else None
        )
        payload_tools_allow = (
            _json_field(payload.get("toolsAllow"))
            if (payload_kind == "agentTurn")
            else None
        )
        delivery_mode = _text_field(delivery, "mode") if delivery else None
        delivery_channel = (
            _text_field(delivery, "channel") if delivery else None
        )
        delivery_to = _text_field(delivery, "to") if delivery else None
        delivery_thread_id = (
            _text_field(delivery, "threadId") if delivery else None
        )
        delivery_account_id = (
            _text_field(delivery, "accountId") if delivery else None
        )
        best_effort_val = (
            delivery.get("bestEffort") if delivery else None
        )
        delivery_best_effort = (
            1
            if (delivery and best_effort_val is True)
            else 0
            if (delivery and best_effort_val is False)
            else None
        )
        completion_mode = (
            _text_field(completion_destination, "mode")
            if completion_destination
            else None
        )
        completion_to = (
            _text_field(completion_destination, "to")
            if completion_destination
            else None
        )
        failure_mode = _failure_destination_field(failure_destination, "mode")
        failure_channel = _failure_destination_field(failure_destination, "channel")
        failure_to = _failure_destination_field(failure_destination, "to")
        failure_account_id = _failure_destination_field(
            failure_destination, "accountId"
        )
        include_skipped_val = (
            failure_alert.get("includeSkipped") if failure_alert else None
        )
        failure_alert_include_skipped = (
            1
            if (failure_alert and include_skipped_val is True)
            else 0
            if (failure_alert and include_skipped_val is False)
            else None
        )
        runtime_updated_at_ms = _number_field(job, "updatedAtMs")
        runtime_updated_at_ms = (
            int(runtime_updated_at_ms)
            if runtime_updated_at_ms is not None
            else fallback_time
        )
        update.execute(
            """
            UPDATE cron_jobs
               SET name = ?,
                   enabled = ?,
                   delete_after_run = ?,
                   created_at_ms = ?,
                   agent_id = ?,
                   session_key = ?,
                   schedule_kind = ?,
                   schedule_expr = ?,
                   schedule_tz = ?,
                   every_ms = ?,
                   anchor_ms = ?,
                   at = ?,
                   stagger_ms = ?,
                   session_target = ?,
                   wake_mode = ?,
                   payload_kind = ?,
                   payload_message = ?,
                   payload_model = ?,
                   payload_fallbacks_json = ?,
                   payload_thinking = ?,
                   payload_timeout_seconds = ?,
                   payload_allow_unsafe_external_content = ?,
                   payload_external_content_source_json = ?,
                   payload_light_context = ?,
                   payload_tools_allow_json = ?,
                   delivery_mode = ?,
                   delivery_channel = ?,
                   delivery_to = ?,
                   delivery_thread_id = ?,
                   delivery_account_id = ?,
                   delivery_best_effort = ?,
                   delivery_completion_mode = ?,
                   delivery_completion_to = ?,
                   failure_delivery_mode = ?,
                   failure_delivery_channel = ?,
                   failure_delivery_to = ?,
                   failure_delivery_account_id = ?,
                   failure_alert_disabled = ?,
                   failure_alert_after = ?,
                   failure_alert_channel = ?,
                   failure_alert_to = ?,
                   failure_alert_cooldown_ms = ?,
                   failure_alert_include_skipped = ?,
                   failure_alert_mode = ?,
                   failure_alert_account_id = ?,
                   runtime_updated_at_ms = ?
             WHERE store_key = ?
               AND job_id = ?
            """,
            (
                run_id_str,
                enabled_int,
                delete_after_run,
                created_at_ms,
                agent_id_val,
                session_key_val,
                schedule_kind,
                schedule_expr,
                schedule_tz,
                int(every_ms) if every_ms is not None else None,
                int(anchor_ms) if anchor_ms is not None else None,
                at_val,
                int(stagger_ms) if stagger_ms is not None else None,
                session_target,
                wake_mode,
                payload_kind,
                payload_message,
                payload_model,
                payload_fallbacks,
                payload_thinking,
                int(payload_timeout_seconds)
                if payload_timeout_seconds is not None
                else None,
                payload_allow_unsafe,
                payload_external_content_source,
                payload_light_context,
                payload_tools_allow,
                delivery_mode,
                delivery_channel,
                delivery_to,
                delivery_thread_id,
                delivery_account_id,
                delivery_best_effort,
                completion_mode,
                completion_to,
                failure_mode,
                failure_channel,
                failure_to,
                failure_account_id,
                failure_alert_disabled,
                int(_number_field(failure_alert, "after"))
                if failure_alert and _number_field(failure_alert, "after") is not None
                else None,
                _text_field(failure_alert, "channel") if failure_alert else None,
                _text_field(failure_alert, "to") if failure_alert else None,
                int(_number_field(failure_alert, "cooldownMs"))
                if failure_alert and _number_field(failure_alert, "cooldownMs") is not None
                else None,
                failure_alert_include_skipped,
                _text_field(failure_alert, "mode") if failure_alert else None,
                _text_field(failure_alert, "accountId") if failure_alert else None,
                runtime_updated_at_ms,
                store_key,
                job_id,
            ),
        )


# ── backfillDeliveryQueueEntriesFromEntryJson ─────────────


def backfill_delivery_queue_entries_from_entry_json(
    conn: sqlite3.Connection,
) -> None:
    """Project ``delivery_queue_entries.entry_json`` into canonical columns.

    Mirrors ``backfillDeliveryQueueEntriesFromEntryJson``.
    Only runs on rows where the column projection is
    incomplete (``retry_count = 0`` or any of the
    recovery / route / account columns is NULL).
    """
    if (
        not table_exists(conn, "delivery_queue_entries")
        or not table_has_column(conn, "delivery_queue_entries", "entry_json")
        or not table_has_column(conn, "delivery_queue_entries", "retry_count")
    ):
        return
    # The full UPDATE references every column in the
    # canonical delivery_queue_entries shape; a
    # partial-shape table can't run the projection.
    required = (
        "queue_name",
        "id",
        "entry_json",
        "status",
        "retry_count",
        "last_attempt_at",
        "last_error",
        "recovery_state",
        "platform_send_started_at",
        "entry_kind",
        "session_key",
        "channel",
        "target",
        "account_id",
    )
    if not all(
        table_has_column(conn, "delivery_queue_entries", column)
        for column in required
    ):
        return
    rows = conn.execute(
        """
        SELECT queue_name, id, entry_json
          FROM delivery_queue_entries
         WHERE status <> 'completed'
           AND (retry_count = 0
             OR last_attempt_at IS NULL
             OR last_error IS NULL
             OR recovery_state IS NULL
             OR platform_send_started_at IS NULL
             OR entry_kind IS NULL
             OR session_key IS NULL
             OR channel IS NULL
             OR target IS NULL
             OR account_id IS NULL)
        """
    ).fetchall()
    if not rows:
        return
    update = conn.cursor()
    for row in rows:
        queue_name, id_, entry_json = row[0], row[1], row[2]
        entry = _parse_json_record(entry_json)
        if not entry:
            continue
        session = _record_field(entry, "session")
        route = _record_field(entry, "route")
        delivery_context = _record_field(entry, "deliveryContext")
        entry_kind = _text_field(entry, "kind")
        session_key_val = _text_field(entry, "sessionKey") or (
            _text_field(session, "key") if session else None
        )
        channel_val = (
            _text_field(entry, "channel")
            or (_text_field(route, "channel") if route else None)
            or (
                _text_field(delivery_context, "channel")
                if delivery_context
                else None
            )
        )
        target_val = (
            _text_field(entry, "to")
            or (_text_field(route, "to") if route else None)
            or (
                _text_field(delivery_context, "to")
                if delivery_context
                else None
            )
        )
        account_id_val = (
            _text_field(entry, "accountId")
            or (_text_field(route, "accountId") if route else None)
            or (
                _text_field(delivery_context, "accountId")
                if delivery_context
                else None
            )
        )
        retry_count_val = _number_field(entry, "retryCount")
        retry_count_int = int(retry_count_val) if retry_count_val is not None else 0
        last_attempt_at_val = _number_field(entry, "lastAttemptAt")
        last_attempt_at_int = (
            int(last_attempt_at_val) if last_attempt_at_val is not None else None
        )
        last_error_val = _text_field(entry, "lastError")
        recovery_state_val = _text_field(entry, "recoveryState")
        platform_send_val = _number_field(entry, "platformSendStartedAt")
        platform_send_int = (
            int(platform_send_val) if platform_send_val is not None else None
        )
        update.execute(
            """
            UPDATE delivery_queue_entries
               SET entry_kind = COALESCE(?, entry_kind),
                   session_key = COALESCE(?, session_key),
                   channel = COALESCE(?, channel),
                   target = COALESCE(?, target),
                   account_id = COALESCE(?, account_id),
                   retry_count = ?,
                   last_attempt_at = COALESCE(?, last_attempt_at),
                   last_error = COALESCE(?, last_error),
                   recovery_state = COALESCE(?, recovery_state),
                   platform_send_started_at = COALESCE(?, platform_send_started_at)
             WHERE queue_name = ?
               AND id = ?
            """,
            (
                entry_kind,
                session_key_val,
                channel_val,
                target_val,
                account_id_val,
                retry_count_int,
                last_attempt_at_int,
                last_error_val,
                recovery_state_val,
                platform_send_int,
                queue_name,
                id_,
            ),
        )


# ── ensureOperatorApprovalResolutionRefs ──────────────────
#
# In OpenClaw this lives in legacy-backfills.ts because it
# uses ``ensure_column``. The Python port mirrors that
# placement.


_APPROVAL_RESOLUTION_REF_LENGTH: int = 43


def build_approval_resolution_ref(
    *, approval_id: str, approval_kind: Any
) -> str:
    """Build a stable, transport-shaped reference for an approval.

    Mirrors ``buildApprovalResolutionRef`` from
    ``@openclaw/infra/approval-resolution-ref``. The Python
    port encodes the ``(kind, id)`` pair into a 43-char
    base64url-without-padding string; the same shape is
    checked by ``repair_operator_approval_schema`` in
    ``operator_approval_migration.py``.
    """
    if not isinstance(approval_id, str) or not approval_id:
        raise ValueError("build_approval_resolution_ref: approval_id required")
    if not is_canonical_operator_approval_kind(approval_kind):
        raise ValueError(
            "build_approval_resolution_ref: approval_kind must be canonical"
        )
    digest = hashlib.sha256(f"{approval_kind}:{approval_id}".encode("utf-8")).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if len(encoded) >= _APPROVAL_RESOLUTION_REF_LENGTH:
        return encoded[:_APPROVAL_RESOLUTION_REF_LENGTH]
    return encoded.ljust(_APPROVAL_RESOLUTION_REF_LENGTH, "A")


def ensure_operator_approval_resolution_refs(conn: sqlite3.Connection) -> None:
    """Add + backfill the ``resolution_ref`` column on ``operator_approvals``.

    Mirrors ``ensureOperatorApprovalResolutionRefs`` from
    ``openclaw-state-db-legacy-backfills.ts``. The Python
    port runs inside a single ``BEGIN IMMEDIATE`` so the
    column add, row backfill, and unique-index create are
    atomic. Rows whose ``kind`` is not canonical raise a
    clear error (the rebuild above should have run first).
    """
    if not table_exists(conn, "operator_approvals"):
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        ensure_column(conn, "operator_approvals", "resolution_ref TEXT")
        rows = conn.execute(
            "SELECT approval_id, kind, resolution_ref FROM operator_approvals"
        ).fetchall()
        update = conn.cursor()
        for row in rows:
            approval_id = row[0]
            kind = row[1]
            current = row[2]
            if not isinstance(approval_id, str) or not is_canonical_operator_approval_kind(
                kind
            ):
                raise RuntimeError(
                    "operator approval row cannot be assigned a transport reference"
                )
            new_ref = build_approval_resolution_ref(
                approval_id=approval_id, approval_kind=kind
            )
            if current != new_ref:
                update.execute(
                    "UPDATE operator_approvals SET resolution_ref = ? "
                    "WHERE approval_id = ?",
                    (new_ref, approval_id),
                )
        # Namespace-conflict probe: no two rows where one's
        # approval_id is another row's resolution_ref.
        conflict = conn.execute(
            "SELECT 1 FROM operator_approvals AS canonical "
            "JOIN operator_approvals AS referenced "
            "ON canonical.approval_id = referenced.resolution_ref "
            "WHERE canonical.approval_id <> referenced.approval_id "
            "LIMIT 1"
        ).fetchone()
        if conflict:
            raise RuntimeError(
                "operator approval ids conflict with durable transport references"
            )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "idx_operator_approvals_resolution_ref "
            "ON operator_approvals(resolution_ref);"
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── backfillLegacyManagedImageRoots (private helper) ──────
#
# OpenClaw keeps this as a module-private helper; the
# Python port mirrors that placement. The shipped
# ``managed_outgoing_image_records`` table had no shipped
# writer; the helper recovers the original media root from
# ``record_json`` and discards malformed rows.


def _resolve_legacy_managed_image_root(record_json: Any) -> Optional[str]:
    """Resolve the legacy media-root from a ``record_json`` blob.

    Mirrors ``resolveLegacyManagedImageRoot`` in
    ``openclaw-state-db-schema-additive.ts``. Returns the
    absolute media-root path or ``None`` when the record
    doesn't carry enough information to recover it.
    """
    record = _parse_json_record(record_json)
    if not record:
        return None
    original = _record_field(record, "original")
    if not original:
        return None
    media_root = original.get("mediaRoot")
    if isinstance(media_root, str) and media_root.strip():
        return os.path.abspath(media_root)
    original_path = original.get("path")
    if not isinstance(original_path, str) or not original_path.strip():
        return None
    resolved_original = os.path.abspath(original_path)
    return os.path.dirname(os.path.dirname(os.path.dirname(resolved_original)))


def _backfill_legacy_managed_image_roots(conn: sqlite3.Connection) -> None:
    """Backfill ``managed_outgoing_image_records.original_media_root``.

    Mirrors ``backfillLegacyManagedImageRoots`` (private
    helper in OpenClaw). Updates rows with a recoverable
    media root; deletes rows that have no shipped writer
    and a malformed ``record_json`` (they'd otherwise
    wedge every database open).
    """
    rows = conn.execute(
        "SELECT attachment_id, record_json FROM managed_outgoing_image_records"
    ).fetchall()
    update_root = conn.cursor()
    delete_record = conn.cursor()
    for row in rows:
        attachment_id, record_json = row[0], row[1]
        media_root = _resolve_legacy_managed_image_root(record_json)
        if media_root:
            update_root.execute(
                "UPDATE managed_outgoing_image_records "
                "SET original_media_root = ? WHERE attachment_id = ?",
                (media_root, attachment_id),
            )
        else:
            delete_record.execute(
                "DELETE FROM managed_outgoing_image_records "
                "WHERE attachment_id = ?",
                (attachment_id,),
            )


__all__ = [
    "_backfill_legacy_managed_image_roots",
    "backfill_acp_replay_estimated_bytes",
    "backfill_cron_jobs_from_job_json",
    "backfill_cron_run_log_entry_json",
    "backfill_delivery_queue_entries_from_entry_json",
    "build_approval_resolution_ref",
    "ensure_operator_approval_resolution_refs",
    "migrate_legacy_cron_delivery_thread_ids",
    "repair_legacy_task_agent_attribution",
    "repair_legacy_task_delivery_statuses",
]
