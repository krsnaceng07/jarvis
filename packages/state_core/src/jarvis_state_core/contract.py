"""State-database contract constants and types.

Mirrors OpenClaw's ``src/state/openclaw-state-db-contract.ts``.
The Python port focuses on the constants and types that ship as
the public surface of the state DB; heavy behavior lives in
``database.py`` + ``readonly.py`` + ``lease.py``.

Public surface:
- ``STATE_SCHEMA_VERSION`` — current canonical schema version
- ``STATE_STRICT_SCHEMA_VERSION`` — STRICT-tables threshold
- ``SQLITE_BUSY_TIMEOUT_MS`` — default busy timeout
- ``DATABASE_SCHEMA_DOCS_URL`` — user-facing guide URL
- ``StateDatabaseHandle`` — runtime handle
- ``StateDatabaseOptions`` — path / env overrides (Python
  re-uses ``StateDatabaseOptions`` from ``database.py``)
- ``StateDatabaseSchemaMigration`` — typed migration kind
- ``StateDatabaseSchemaMigrationKind`` — closed set of kinds
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

# Current canonical schema version. Bumping this is a
# breaking change and must follow the user-discussion rule
# in AGENTS.md (any SQLite change requiring a schema-version
# bump needs explicit user discussion and acceptance before
# implementation).
STATE_SCHEMA_VERSION: int = 1
# STRICT-tables threshold: databases at or above this
# version use SQLite STRICT typing. Below it the runtime
# tolerates legacy column types.
STATE_STRICT_SCHEMA_VERSION: int = 1
# Default busy timeout (ms) for shared state DB
# connections. Matches OpenClaw's
# ``OPENCLAW_SQLITE_BUSY_TIMEOUT_MS``.
SQLITE_BUSY_TIMEOUT_MS: int = 5_000
# User-facing guide URL for schema refusals.
DATABASE_SCHEMA_DOCS_URL: str = "https://docs.jarvis.ai/reference/database-schemas"


# Closed set of schema-migration kinds. Mirrors
# OpenClaw's ``OpenClawStateDatabaseSchemaMigrationKind``.
StateDatabaseSchemaMigrationKind = Literal[
    "agent-databases-composite-primary-key",
    "audit-events-v2",
    "operator-approvals-system-agent",
    "session-watch-cursor-provenance-v4",
    "strict-tables-v3",
]


class _StateDatabaseSchemaMigrationRequired(TypedDict, total=True):
    kind: StateDatabaseSchemaMigrationKind
    path: str


class StateDatabaseSchemaMigration(_StateDatabaseSchemaMigrationRequired, total=False):
    extra: dict[str, Any]


@dataclass
class StateDatabaseHandle:
    """Open shared SQLite database handle + lifecycle.

    Mirrors OpenClaw's ``OpenClawStateDatabase``. The
    ``db`` is the underlying ``sqlite3.Connection``; the
    ``path`` is the canonical file path.
    """

    db: Any
    path: str


__all__ = [
    "DATABASE_SCHEMA_DOCS_URL",
    "SQLITE_BUSY_TIMEOUT_MS",
    "STATE_SCHEMA_VERSION",
    "STATE_STRICT_SCHEMA_VERSION",
    "StateDatabaseHandle",
    "StateDatabaseSchemaMigration",
    "StateDatabaseSchemaMigrationKind",
]
