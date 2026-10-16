"""Read-only state database helper.

Mirrors OpenClaw's ``src/state/openclaw-state-db-readonly.ts``.
The TS port opens a fresh ``DatabaseSync`` in ``readOnly``
mode, sets ``busy_timeout``, asserts the schema version, and
hands the handle to a callback; the Python port is identical
but uses ``sqlite3``'s URI mode to open the file readonly.

Why a separate readonly helper: CLI metadata reads can
overlap a live Gateway. Keeping them off schema repair,
journal-mode setup, checkpoints, and permission mutation
owned by writers means readonly callers can never block
or corrupt the writable lifecycle.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Callable, Optional, TypeVar

from .contract import (
    SQLITE_BUSY_TIMEOUT_MS,
    STATE_SCHEMA_VERSION,
    StateDatabaseHandle,
)
from .paths import resolve_state_sqlite_path

T = TypeVar("T")


class _NewerSchemaVersionError(Exception):
    """Raised when the on-disk schema version exceeds the runtime's max."""

    def __init__(self, label: str, pathname: str, found: int, expected: int) -> None:
        super().__init__(
            f"{label} at {pathname} has schema version {found}; "
            f"runtime supports up to {expected}. Upgrade the runtime "
            "or run ``jarvis doctor --fix``."
        )
        self.label = label
        self.pathname = pathname
        self.found = found
        self.expected = expected


def _read_sqlite_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    if not row:
        return 0
    return int(row[0] or 0)


def _open_readonly_sqlite(pathname: str) -> sqlite3.Connection:
    """Open a SQLite connection in read-only mode.

    Uses URI mode so concurrent writers can keep going.
    The connection has row factory set to ``sqlite3.Row``
    for parity with the writable helpers.
    """
    # ``mode=ro`` opens the file read-only; ``file:`` URI
    # prefix is required for mode/extra params.
    uri = f"file:{pathname}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def with_state_database_read_only(
    operation: Callable[[StateDatabaseHandle], T],
    *,
    env: Optional[dict[str, str]] = None,
    path: Optional[str] = None,
) -> T:
    """Open the shared state database read-only + hand it to ``operation``.

    Mirrors ``withOpenClawStateDatabaseReadOnly``. The
    ``operation`` callback receives a ``StateDatabaseHandle``
    ({db, path}) and the helper handles the connection
    lifecycle + busy-timeout pragma + schema-version
    assertion + close.

    The connection has no chance to mutate the database
    file. Schema-version refusals are raised as
    ``_NewerSchemaVersionError``; older schemas (read-only)
    are tolerated.
    """
    if not isinstance(operation, dict) and not callable(operation):
        raise TypeError("with_state_database_read_only: operation must be callable")
    pathname = os.path.abspath(path or resolve_state_sqlite_path(env or os.environ))
    conn = _open_readonly_sqlite(pathname)
    try:
        conn.execute(f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_MS)}")
        user_version = _read_sqlite_user_version(conn)
        if user_version > STATE_SCHEMA_VERSION:
            raise _NewerSchemaVersionError(
                "Jarvis state database",
                pathname,
                user_version,
                STATE_SCHEMA_VERSION,
            )
        return operation(StateDatabaseHandle(db=conn, path=pathname))
    finally:
        conn.close()


__all__ = [
    "with_state_database_read_only",
]
