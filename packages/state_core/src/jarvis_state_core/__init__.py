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
  watch cursors + upstream links + state leases)

Public API:
- ``StateDatabase`` — the main entry
- ``StateDatabaseOptions`` — the DI bag
- ``run_write_transaction`` — per-store-path FIFO write
  transaction runner
- ``run_queued_store_write`` — per-key FIFO runner
- ``Query`` / ``SelectBuilder`` / ``InsertBuilder`` /
  ``UpdateBuilder`` / ``DeleteBuilder`` — fluent SQL
  builder helpers
- ``ensure_schema`` — schema bootstrap
- ``reset_state_for_tests`` — clear the singleton

Python adaptations (documented in code):
- TS Kysely → direct ``sqlite3`` SQL via a tiny fluent
  builder. The Python port exposes the most common
  cases (select / insert / update / delete + where /
  order by / limit / returning) on top of direct
  ``sqlite3`` SQL.
- TS AsyncLocalStorage → Python ``contextvars.ContextVar``
  (the active-writer reentrancy context)
- TS ``Map`` → Python ``dict``
- TS ``setTimeout(..., unref)`` → Python
  ``threading.Timer`` (daemon, fire-and-forget)
"""
from __future__ import annotations

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

__all__ = [
    "DeleteBuilder",
    "InsertBuilder",
    "Query",
    "SelectBuilder",
    "StateDatabase",
    "StateDatabaseOptions",
    "UpdateBuilder",
    "ensure_schema",
    "reset_state_for_tests",
    "run_queued_store_write",
    "run_write_transaction",
]
