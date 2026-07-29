"""Canonical SQLite state database for the JARVIS Brain Core.

Mirrors a focused subset of OpenClaw's
``src/state/openclaw-state-db.ts`` (the connection factory
+ transaction runner + readonly helpers). The Python
port focuses on:

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
from .database import (
    DeleteBuilder,
    InsertBuilder,
    Query,
    SelectBuilder,
    StateDatabase,
    StateDatabaseOptions,
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
    "MIN_LEASE_MS",
    "Query",
    "RELEASE_RETRY_TIMEOUT_MS",
    "SQLITE_BUSY_TIMEOUT_MS",
    "STATE_DIR_MODE",
    "STATE_FILE_MODE",
    "STATE_SCHEMA_VERSION",
    "STATE_STRICT_SCHEMA_VERSION",
    "SelectBuilder",
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
    "close_agent_database",
    "close_all_agent_databases",
    "can_repair_legacy_audit_events_schema",
    "ensure_agent_database_permissions",
    "ensure_schema",
    "ensure_state_permissions",
    "has_canonical_audit_events_schema",
    "inspect_agent_database_owner",
    "is_agent_database_open",
    "open_agent_database",
    "repair_audit_events_schema",
    "reset_agent_database_state_for_tests",
    "reset_lease_state_for_tests",
    "reset_state_for_tests",
    "resolve_agent_sqlite_dir",
    "resolve_agent_sqlite_path",
    "resolve_state_root_dir",
    "resolve_state_sqlite_dir",
    "resolve_state_sqlite_path",
    "run_queued_store_write",
    "run_write_transaction",
    "with_state_database_read_only",
    "with_state_lease",
]
