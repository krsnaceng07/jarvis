"""Canonical SQLite state database for the JARVIS Brain Core.

Mirrors a focused subset of OpenClaw's
``src/state/openclaw-state-db.ts`` + the migration +
additive + maintenance modules under ``src/state/``. The
Python port focuses on:

- the ``StateDatabase`` context (connection factory +
  busy-timeout + WAL + foreign-keys pragmas)
- the ``run_write_transaction`` runner that wraps a
  callback in a per-store-path FIFO write transaction
- the ``run_queued_store_write`` runner that serializes
  work per-key within a single process
- the Kysely-like ``Query`` helper for SELECT / INSERT /
  UPDATE / DELETE statements
- the ``ensure_schema`` bootstrap helper that creates
  the canonical baseline tables (state events + heads +
  watch cursors + upstream links + lease)
- the ``with_state_database_read_only`` helper that
  opens a read-only handle for CLI metadata reads
- the ``with_state_lease`` runner that acquires a
  host-owned SQLite lease for trusted work
- the ``repair_audit_events_schema`` helper that
  migrates the legacy ``audit_events`` table to the v2
  shape
- the ``open_agent_database`` per-agent DB helper
- the ``schema_helpers`` module: table / column / index
  probes + the ``ensure_column`` additive helper
- the ``operator_approval_migration`` module: rebuilds
  the ``operator_approvals`` table when its kind
  constraint is legacy (2-kind vs 3-kind)
- the ``session_watch_migration`` module: migrates
  legacy ambient-group sentinels to the schema-v4 shape
- the ``legacy_backfills`` module: row-level projections
  for the shipped legacy column shapes
- the ``schema_additive`` module: 100+ ``ensureColumn``
  calls that grow every released table to the canonical
  column set
- the ``schema_repair`` module: drop legacy tables,
  rebuild the agent_databases PK, assert canonical
  shape, detect pending migrations
- the ``maintenance`` module: offline VACUUM / REINDEX
  preconditions + integrity verification errors

Public API:
- ``StateDatabase`` — the main entry
- ``StateDatabaseOptions`` — the DI bag
- ``run_write_transaction`` — per-store-path FIFO write
  transaction runner
- ``run_queued_store_write`` — per-key FIFO runner
- ``Query`` / ``Select/Insert/Update/Delete`` Kysely-like builder
- ``ensure_schema`` — schema bootstrap
- ``reset_state_for_tests`` — clear the singleton
- ``with_state_database_read_only`` — read-only handle
- ``with_state_lease`` — SQLite-backed lease
- ``StateLeaseError`` + ``StateLeaseErrorCode``
- ``repair_audit_events_schema``
- ``open_agent_database`` + ``close_agent_database``
- ``ensure_column`` + ``table_exists`` + ``table_has_column``
  + ``table_primary_key_columns`` + ``index_exists`` —
  schema probes
- ``repair_operator_approval_schema`` + ``detect_operator_approval_schema_migration``
- ``migrate_session_watch_cursor_provenance``
  + ``needs_session_watch_cursor_provenance_migration``
- ``ensure_additive_state_columns`` — full additive ensure
- ``repair_agent_databases_composite_primary_key``
  + ``drop_legacy_state_tables``
  + ``assert_canonical_state_schema_shape``
  + ``detect_jarvis_state_database_schema_migrations``
- ``assert_jarvis_state_database_for_maintenance``
  + ``create_jarvis_database_verification_error``

Python adaptations (documented in code):
- TS Kysely → direct ``sqlite3`` SQL via a tiny fluent
  builder. The Python port exposes the most common
  cases (select / insert / update / delete + where /
  order by / limit / returning) on top of direct
  ``sqlite3`` SQL.
- TS AsyncLocalStorage → Python ``contextvars.ContextVar``
  (the active-writer reentrancy context)
- TS ``Map`` → Python ``dict``
- TS ``AbortSignal`` → Python ``threading.Event``
- TS ``randomUUID`` → Python ``uuid.uuid4``
- TS ``setTimeout(..., unref)`` → Python
  ``threading.Timer`` (daemon, fire-and-forget)
- TS ``DatabaseSync`` → Python ``sqlite3.Connection``
  (the legacy-backfills + additive ensure run as plain
  SQL on an open connection; the caller owns the
  surrounding ``BEGIN IMMEDIATE`` transaction)
"""
from __future__ import annotations

from .agent_db import (
    AgentDatabaseHandle,
    AgentDatabaseOptions,
    AgentDatabaseOwnerStatus,
    close_agent_database,
    close_all_agent_databases,
    inspect_agent_database_owner,
    is_agent_database_open,
    open_agent_database,
    reset_agent_database_state_for_tests,
)
from .audit_migration import (
    AUDIT_EVENT_LEGACY_COLUMNS,
    AUDIT_EVENT_LEGACY_REQUIRED_NOT_NULL_COLUMNS,
    AUDIT_EVENT_STATE_SCHEMA_VERSION,
    AUDIT_EVENT_V2_COLUMNS,
    AUDIT_EVENT_V2_REQUIRED_NOT_NULL_COLUMNS,
    can_repair_legacy_audit_events_schema,
    has_canonical_audit_events_schema,
    repair_audit_events_schema,
)
from .contract import (
    DATABASE_SCHEMA_DOCS_URL,
    SQLITE_BUSY_TIMEOUT_MS,
    STATE_SCHEMA_VERSION,
    STATE_STRICT_SCHEMA_VERSION,
    StateDatabaseHandle,
    StateDatabaseSchemaMigration,
    StateDatabaseSchemaMigrationKind,
)
from .database import StateDatabaseOptions
from .database import (
    DeleteBuilder,
    InsertBuilder,
    Query,
    SelectBuilder,
    StateDatabase,
    UpdateBuilder,
    ensure_schema,
    reset_state_for_tests,
    run_queued_store_write,
    run_write_transaction,
)
from .lease import (
    ACQUIRE_BACKOFF,
    LEASE_DB_BUSY_TIMEOUT_MS,
    MIN_LEASE_MS,
    RELEASE_RETRY_TIMEOUT_MS,
    StateLeaseContext,
    StateLeaseError,
    StateLeaseErrorCode,
    StateLeaseOptions,
    reset_lease_state_for_tests,
    with_state_lease,
)
from .legacy_backfills import (
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
from .maintenance import (
    STATE_MAINTENANCE_SCHEMA_COMPATIBILITY,
    assert_jarvis_state_database_for_maintenance,
    assert_supported_schema_version,
    create_jarvis_database_verification_error,
    resolve_database_path,
)
from .operator_approval_migration import (
    OPERATOR_APPROVAL_COLUMNS,
    OperatorApprovalKind,
    assert_canonical_operator_approval_kinds,
    detect_operator_approval_schema_migration,
    has_canonical_operator_approval_kinds,
    has_exact_legacy_operator_approval_schema,
    is_canonical_operator_approval_kind,
    repair_operator_approval_schema,
)
from .paths import (
    resolve_agent_sqlite_dir,
    resolve_agent_sqlite_path,
    resolve_state_root_dir,
    resolve_state_sqlite_dir,
    resolve_state_sqlite_path,
)
from .permissions import (
    STATE_DIR_MODE,
    STATE_FILE_MODE,
    ensure_agent_database_permissions,
    ensure_state_permissions,
)
from .readonly import with_state_database_read_only
from .schema_additive import ensure_additive_state_columns
from .schema_helpers import (
    ensure_column,
    index_exists,
    table_exists,
    table_has_column,
    table_index_list,
    table_primary_key_columns,
)
from .schema_repair import (
    assert_canonical_state_schema_shape,
    can_repair_agent_databases_primary_key,
    detect_jarvis_state_database_schema_migrations,
    drop_legacy_state_tables,
    has_canonical_agent_databases_primary_key,
    mark_current_state_schema_version,
    repair_agent_databases_composite_primary_key,
)
from .session_watch_migration import (
    LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX,
    SESSION_WATCH_PROVENANCE_AMBIENT_GROUP,
    SESSION_WATCH_PROVENANCE_EXPLICIT,
    SESSION_WATCH_PROVENANCE_SCHEMA_VERSION,
    SessionWatchCursorProvenanceMigrationResult,
    decode_legacy_ambient_watch_marker_key,
    has_legacy_ambient_watch_sentinels,
    migrate_session_watch_cursor_provenance,
    needs_session_watch_cursor_provenance_migration,
)

__all__ = [
    "ACQUIRE_BACKOFF",
    "AUDIT_EVENT_LEGACY_COLUMNS",
    "AUDIT_EVENT_LEGACY_REQUIRED_NOT_NULL_COLUMNS",
    "AUDIT_EVENT_STATE_SCHEMA_VERSION",
    "AUDIT_EVENT_V2_COLUMNS",
    "AUDIT_EVENT_V2_REQUIRED_NOT_NULL_COLUMNS",
    "AgentDatabaseHandle",
    "AgentDatabaseOptions",
    "AgentDatabaseOwnerStatus",
    "DATABASE_SCHEMA_DOCS_URL",
    "DeleteBuilder",
    "InsertBuilder",
    "LEASE_DB_BUSY_TIMEOUT_MS",
    "LEGACY_AMBIENT_GROUP_WATCH_MARKER_PREFIX",
    "MIN_LEASE_MS",
    "OPERATOR_APPROVAL_COLUMNS",
    "OperatorApprovalKind",
    "Query",
    "RELEASE_RETRY_TIMEOUT_MS",
    "SESSION_WATCH_PROVENANCE_AMBIENT_GROUP",
    "SESSION_WATCH_PROVENANCE_EXPLICIT",
    "SESSION_WATCH_PROVENANCE_SCHEMA_VERSION",
    "SQLITE_BUSY_TIMEOUT_MS",
    "STATE_DIR_MODE",
    "STATE_FILE_MODE",
    "STATE_MAINTENANCE_SCHEMA_COMPATIBILITY",
    "STATE_SCHEMA_VERSION",
    "STATE_STRICT_SCHEMA_VERSION",
    "SelectBuilder",
    "SessionWatchCursorProvenanceMigrationResult",
    "StateDatabase",
    "StateDatabaseHandle",
    "StateDatabaseOptions",
    "StateDatabaseSchemaMigration",
    "StateDatabaseSchemaMigrationKind",
    "StateLeaseContext",
    "StateLeaseError",
    "StateLeaseErrorCode",
    "StateLeaseOptions",
    "UpdateBuilder",
    "assert_canonical_operator_approval_kinds",
    "assert_canonical_state_schema_shape",
    "assert_jarvis_state_database_for_maintenance",
    "assert_supported_schema_version",
    "backfill_acp_replay_estimated_bytes",
    "backfill_cron_jobs_from_job_json",
    "backfill_cron_run_log_entry_json",
    "backfill_delivery_queue_entries_from_entry_json",
    "build_approval_resolution_ref",
    "can_repair_agent_databases_primary_key",
    "can_repair_legacy_audit_events_schema",
    "close_agent_database",
    "close_all_agent_databases",
    "create_jarvis_database_verification_error",
    "decode_legacy_ambient_watch_marker_key",
    "detect_jarvis_state_database_schema_migrations",
    "detect_operator_approval_schema_migration",
    "drop_legacy_state_tables",
    "ensure_additive_state_columns",
    "ensure_agent_database_permissions",
    "ensure_column",
    "ensure_operator_approval_resolution_refs",
    "ensure_schema",
    "ensure_state_permissions",
    "has_canonical_agent_databases_primary_key",
    "has_canonical_audit_events_schema",
    "has_canonical_operator_approval_kinds",
    "has_exact_legacy_operator_approval_schema",
    "has_legacy_ambient_watch_sentinels",
    "index_exists",
    "inspect_agent_database_owner",
    "is_agent_database_open",
    "is_canonical_operator_approval_kind",
    "mark_current_state_schema_version",
    "migrate_legacy_cron_delivery_thread_ids",
    "migrate_session_watch_cursor_provenance",
    "needs_session_watch_cursor_provenance_migration",
    "open_agent_database",
    "repair_agent_databases_composite_primary_key",
    "repair_audit_events_schema",
    "repair_legacy_task_agent_attribution",
    "repair_legacy_task_delivery_statuses",
    "repair_operator_approval_schema",
    "reset_agent_database_state_for_tests",
    "reset_lease_state_for_tests",
    "reset_state_for_tests",
    "resolve_agent_sqlite_dir",
    "resolve_agent_sqlite_path",
    "resolve_database_path",
    "resolve_state_root_dir",
    "resolve_state_sqlite_dir",
    "resolve_state_sqlite_path",
    "run_queued_store_write",
    "run_write_transaction",
    "table_exists",
    "table_has_column",
    "table_index_list",
    "table_primary_key_columns",
    "with_state_database_read_only",
    "with_state_lease",
]
