"""Best-effort shared-state registry for adopted upstream sessions.

Mirrors OpenClaw's ``src/sessions/session-upstream-links.ts``.

The OpenClaw source uses Kysely against the
``openclaw-state-db`` schema with two tables:
``session_upstream_links`` (per-session, per-agent upstream
adoption metadata) and ``session_watch_cursors`` (which keys
are being polled). The Python port uses a direct
``sqlite3.Connection`` (stdlib) against the same canonical
schema.

Python adaptations (documented in code):
- TS ``Kysely`` query builder → direct ``sqlite3`` SQL. The
  OpenClaw queries compile to a small set of well-known
  ``SELECT`` / ``INSERT … ON CONFLICT`` / ``UPDATE`` /
  ``DELETE`` statements; we keep the SQL explicit so the
  port reads the same as the TS source.
- TS ``DatabaseSync`` (Node ``node:sqlite``) → Python
  ``sqlite3.Connection`` (DB-API 2.0). The connection is
  injected via the ``connection_factory`` option so the host
  can wire the canonical state DB (``~/.jarvis/state/jarvis.sqlite``)
  and tests can use ``:memory:`` or a temp file.
- TS ``OpenClawStateDatabaseOptions`` is replaced by an options
  dataclass that carries the connection factory, env vars, and
  an optional ``now``/``expected_updated_at`` override used by
  the CAS-update path.
- TS ``SessionUpstreamJsonValue`` → Python ``Any`` (the value
  is JSON-serialized on the way in and JSON-parsed on the way
  out; the in-memory shape is the parsed JSON value).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypedDict

logger = logging.getLogger("jarvis.sessions.upstream_links")

# Schema constants. Mirrors the OpenClaw table names; the host
# is responsible for ensuring the schema exists (the test harness
# uses ``ensure_schema()`` below to bootstrap a fresh DB).
TABLE_UPSTREAM_LINKS = "session_upstream_links"
TABLE_WATCH_CURSORS = "session_watch_cursors"


class SessionUpstreamLink(TypedDict, total=False):
    sessionKey: str
    agentId: str
    catalogId: str
    hostId: str
    threadId: str
    upstreamKind: str
    upstreamRef: Any
    marker: Optional[Any]
    lastScannedAt: int
    createdAt: int
    updatedAt: int


class SessionUpstreamLinkInput(TypedDict, total=False):
    sessionKey: str
    agentId: str
    catalogId: str
    hostId: str
    threadId: str
    upstreamKind: str
    upstreamRef: Any
    marker: Any


@dataclass
class SessionUpstreamLinkOptions:
    """Connection-factory + override bag for the upstream-link helpers.

    Mirrors ``OpenClawStateDatabaseOptions`` plus the per-call
    ``now``/``expectedUpdatedAt`` overrides. The factory is
    called lazily and the returned connection is closed in a
    ``with`` block, so the host can pass an in-memory or
    file-backed DB.
    """

    connection_factory: Optional[Callable[[], sqlite3.Connection]] = None
    env: Optional[dict[str, str]] = None
    now: Optional[int] = None
    expected_updated_at: Optional[int] = None

    # Test-only flag: when ``True``, the helpers do not auto-bootstrap
    # the schema. Production code paths leave this ``False`` and let
    # the host ensure the tables exist.
    skip_schema_ensure: bool = False


@dataclass
class _DbState:
    """Per-connection-state cache. The OpenClaw state DB uses one
    shared connection per process; we mirror that with a thread-local
    lazy handle so the test harness can swap DBs per test.
    """

    lock: threading.RLock = field(default_factory=threading.RLock)


_thread_local = threading.local()


def _open_connection(
    options: SessionUpstreamLinkOptions,
) -> sqlite3.Connection:
    """Open a connection per call. The factory is called fresh;
    callers that need a longer-lived connection should use the
    same factory twice and get a new connection each time.
    """
    if options.connection_factory is None:
        raise ValueError(
            "session_upstream_links: connection_factory is required "
            "(host must wire the canonical state DB)"
        )
    conn = options.connection_factory()
    # Use the row factory so reads return dicts.
    conn.row_factory = sqlite3.Row
    return conn


# ── Schema bootstrap (test / first-use helper) ───────────────


SCHEMA_UPSTREAM_LINKS = """
CREATE TABLE IF NOT EXISTS session_upstream_links (
    session_key        TEXT NOT NULL,
    agent_id           TEXT NOT NULL,
    catalog_id         TEXT NOT NULL,
    host_id            TEXT NOT NULL,
    thread_id          TEXT NOT NULL,
    upstream_kind      TEXT NOT NULL,
    upstream_ref_json  TEXT NOT NULL,
    last_marker_json   TEXT,
    last_scanned_at    INTEGER,
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    PRIMARY KEY (session_key, agent_id)
)
""".strip()

SCHEMA_WATCH_CURSORS = """
CREATE TABLE IF NOT EXISTS session_watch_cursors (
    target_session_key TEXT NOT NULL,
    watcher_session_key TEXT NOT NULL,
    PRIMARY KEY (target_session_key, watcher_session_key)
)
""".strip()


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create the upstream-link and watch-cursor tables if missing.

    Test-only / first-use helper. The host is responsible for
    running the canonical schema migration; this helper is
    provided for tests and for one-time lazy bootstrap.
    """
    connection.executescript(
        f"{SCHEMA_UPSTREAM_LINKS};\n{SCHEMA_WATCH_CURSORS};"
    )
    connection.commit()


def _ensure_schema_for_options(options: SessionUpstreamLinkOptions) -> None:
    if options.skip_schema_ensure:
        return
    if options.connection_factory is None:
        return
    conn = options.connection_factory()
    try:
        conn.row_factory = sqlite3.Row
        ensure_schema(conn)
    finally:
        conn.close()


# ── Row mapping ─────────────────────────────────────────────


def _parse_json_value(value: Optional[str]) -> Any:
    """Parse a JSON column value, returning ``None`` for ``NULL`` or bad input.

    Mirrors the private ``parseJson`` helper.
    """
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _row_to_link(row: sqlite3.Row) -> SessionUpstreamLink:
    """Map a ``session_upstream_links`` row to the public dict shape.

    Mirrors ``rowToSessionUpstreamLink``.
    """
    last_scanned_at = row["last_scanned_at"]
    link: SessionUpstreamLink = {
        "sessionKey": row["session_key"],
        "agentId": row["agent_id"],
        "catalogId": row["catalog_id"],
        "hostId": row["host_id"],
        "threadId": row["thread_id"],
        "upstreamKind": row["upstream_kind"],
        "upstreamRef": _parse_json_value(row["upstream_ref_json"]),
        "marker": _parse_json_value(row["last_marker_json"]),
        "createdAt": int(row["created_at"] or 0),
        "updatedAt": int(row["updated_at"] or 0),
    }
    if last_scanned_at is not None:
        link["lastScannedAt"] = int(last_scanned_at)
    return link


# ── Public surface ──────────────────────────────────────────


def upsert_session_upstream_link(
    input_data: SessionUpstreamLinkInput,
    options: Optional[SessionUpstreamLinkOptions] = None,
) -> bool:
    """Insert or update a session upstream link.

    Mirrors ``upsertSessionUpstreamLink``. Returns ``True`` on
    success, ``False`` when the DB write failed (warning logged).
    On conflict (same ``session_key`` + ``agent_id``), the row is
    updated; if the upstream source identity changed
    (``thread_id``, ``host_id``, ``upstream_kind``, or
    ``upstream_ref_json``), the marker is rebased to the new
    baseline and the ``last_scanned_at`` cursor is reset to
    ``NULL`` so a refresh starts from scratch.
    """
    options = options or SessionUpstreamLinkOptions()
    _ensure_schema_for_options(options)
    now = options.now if options.now is not None else int(time.time() * 1000)
    upstream_ref_json = json.dumps(input_data["upstreamRef"])
    marker_json = json.dumps(input_data["marker"])
    try:
        with _open_connection(options) as conn:
            conn.execute(
                f"""
                INSERT INTO {TABLE_UPSTREAM_LINKS} (
                    session_key, agent_id, catalog_id, host_id, thread_id,
                    upstream_kind, upstream_ref_json, last_marker_json,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT (session_key, agent_id) DO UPDATE SET
                    agent_id = excluded.agent_id,
                    catalog_id = excluded.catalog_id,
                    host_id = excluded.host_id,
                    thread_id = excluded.thread_id,
                    upstream_kind = excluded.upstream_kind,
                    upstream_ref_json = excluded.upstream_ref_json,
                    last_marker_json = CASE
                        WHEN {TABLE_UPSTREAM_LINKS}.thread_id != excluded.thread_id
                            OR {TABLE_UPSTREAM_LINKS}.host_id != excluded.host_id
                            OR {TABLE_UPSTREAM_LINKS}.upstream_kind != excluded.upstream_kind
                            OR {TABLE_UPSTREAM_LINKS}.upstream_ref_json != excluded.upstream_ref_json
                        THEN excluded.last_marker_json
                        ELSE {TABLE_UPSTREAM_LINKS}.last_marker_json
                    END,
                    last_scanned_at = CASE
                        WHEN {TABLE_UPSTREAM_LINKS}.thread_id != excluded.thread_id
                            OR {TABLE_UPSTREAM_LINKS}.host_id != excluded.host_id
                            OR {TABLE_UPSTREAM_LINKS}.upstream_kind != excluded.upstream_kind
                            OR {TABLE_UPSTREAM_LINKS}.upstream_ref_json != excluded.upstream_ref_json
                        THEN NULL
                        ELSE {TABLE_UPSTREAM_LINKS}.last_scanned_at
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    input_data["sessionKey"],
                    input_data["agentId"],
                    input_data["catalogId"],
                    input_data["hostId"],
                    input_data["threadId"],
                    input_data["upstreamKind"],
                    upstream_ref_json,
                    marker_json,
                    now,
                    now,
                ),
            )
            conn.commit()
        return True
    except sqlite3.Error as error:
        logger.warning("failed to upsert session upstream link: %s", error)
        return False


def read_session_upstream_link(
    session_key: str,
    agent_id: str,
    options: Optional[SessionUpstreamLinkOptions] = None,
) -> Optional[SessionUpstreamLink]:
    """Read a single session upstream link, or ``None`` if missing.

    Mirrors ``readSessionUpstreamLink``.
    """
    options = options or SessionUpstreamLinkOptions()
    _ensure_schema_for_options(options)
    try:
        with _open_connection(options) as conn:
            cursor = conn.execute(
                f"SELECT * FROM {TABLE_UPSTREAM_LINKS} "
                "WHERE session_key = ? AND agent_id = ?",
                (session_key, agent_id),
            )
            row = cursor.fetchone()
            return _row_to_link(row) if row is not None else None
    except sqlite3.Error as error:
        logger.warning("failed to read session upstream link: %s", error)
        return None


def update_session_upstream_link_marker(
    session_key: str,
    agent_id: str,
    marker: Any,
    options: Optional[SessionUpstreamLinkOptions] = None,
) -> bool:
    """Update the marker for a session upstream link.

    Mirrors ``updateSessionUpstreamLinkMarker``. Supports an
    optional ``expected_updated_at`` CAS so a stale scan cannot
    clobber a refresh that landed mid-scan. Returns ``True``
    when the row was actually updated, ``False`` otherwise.
    """
    options = options or SessionUpstreamLinkOptions()
    _ensure_schema_for_options(options)
    now = options.now if options.now is not None else int(time.time() * 1000)
    marker_json = json.dumps(marker)
    try:
        with _open_connection(options) as conn:
            sql = (
                f"UPDATE {TABLE_UPSTREAM_LINKS} "
                "SET last_marker_json = ?, last_scanned_at = ?, updated_at = ? "
                "WHERE session_key = ? AND agent_id = ?"
            )
            params: list[Any] = [marker_json, now, now, session_key, agent_id]
            if options.expected_updated_at is not None:
                sql += " AND updated_at = ?"
                params.append(options.expected_updated_at)
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor.rowcount == 1
    except sqlite3.Error as error:
        logger.warning("failed to update session upstream marker: %s", error)
        return False


def delete_session_upstream_link(
    session_key: str,
    agent_id: str,
    options: Optional[SessionUpstreamLinkOptions] = None,
) -> None:
    """Delete a session upstream link. No-op when the row is missing.

    Mirrors ``deleteSessionUpstreamLink``. The TS version
    returns ``void``; we mirror that.
    """
    options = options or SessionUpstreamLinkOptions()
    _ensure_schema_for_options(options)
    try:
        with _open_connection(options) as conn:
            conn.execute(
                f"DELETE FROM {TABLE_UPSTREAM_LINKS} "
                "WHERE session_key = ? AND agent_id = ?",
                (session_key, agent_id),
            )
            conn.commit()
    except sqlite3.Error as error:
        logger.warning("failed to delete session upstream link: %s", error)


def list_watched_session_upstream_links(
    options: Optional[SessionUpstreamLinkOptions] = None,
) -> dict[str, list[SessionUpstreamLink]]:
    """List all session upstream links joined with active watch cursors, grouped by catalog.

    Mirrors ``listWatchedSessionUpstreamLinks``. The OpenClaw
    join matches on ``session_key`` only (single resolved
    store agent per key); the Python port preserves that
    semantics and the fail-closed behavior that drops every
    link for any duplicated key (so a cross-agent link can
    never be probed against another agent's cursor).
    """
    options = options or SessionUpstreamLinkOptions()
    _ensure_schema_for_options(options)
    grouped: dict[str, list[SessionUpstreamLink]] = {}
    try:
        with _open_connection(options) as conn:
            cursor = conn.execute(
                f"""
                SELECT DISTINCT links.*
                FROM {TABLE_UPSTREAM_LINKS} AS links
                INNER JOIN {TABLE_WATCH_CURSORS} AS cursors
                    ON cursors.target_session_key = links.session_key
                ORDER BY links.catalog_id ASC, links.session_key ASC
                """
            )
            links = [_row_to_link(row) for row in cursor.fetchall()]
        # Fail closed on the single-agent-per-key invariant.
        key_counts: dict[str, int] = {}
        for link in links:
            key_counts[link["sessionKey"]] = (
                key_counts.get(link["sessionKey"], 0) + 1
            )
        for link in links:
            if (key_counts.get(link["sessionKey"]) or 0) > 1:
                logger.warning(
                    "skipping ambiguous upstream links for %s: "
                    "multiple agents adopt the same key",
                    link["sessionKey"],
                )
                continue
            grouped.setdefault(link["catalogId"], []).append(link)
    except sqlite3.Error as error:
        logger.warning("failed to list watched session upstream links: %s", error)
    return grouped


# ── Watch-cursor registration helper (test convenience) ────
#
# The TS tests use ``registerSessionStateWatch`` from
# session-state-events.ts to seed the watch cursor table. The
# Python port keeps a small helper here so tests can wire the
# watch cursor without pulling in the (38K) session-state-events
# port just to set up test fixtures.


def register_session_upstream_watch(
    *,
    watcher_session_key: str,
    target_session_key: str,
    options: Optional[SessionUpstreamLinkOptions] = None,
) -> bool:
    """Insert a watch-cursor row mapping ``watcher_session_key`` → ``target_session_key``.

    This is a test-facade helper. Production code paths should
    use the dedicated ``registerSessionStateWatch`` from
    ``session-state-events`` (when ported).
    """
    options = options or SessionUpstreamLinkOptions()
    _ensure_schema_for_options(options)
    try:
        with _open_connection(options) as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {TABLE_WATCH_CURSORS} "
                "(target_session_key, watcher_session_key) VALUES (?, ?)",
                (target_session_key, watcher_session_key),
            )
            conn.commit()
        return True
    except sqlite3.Error as error:
        logger.warning("failed to register upstream watch cursor: %s", error)
        return False


__all__ = [
    "SCHEMA_UPSTREAM_LINKS",
    "SCHEMA_WATCH_CURSORS",
    "SessionUpstreamLink",
    "SessionUpstreamLinkInput",
    "SessionUpstreamLinkOptions",
    "TABLE_UPSTREAM_LINKS",
    "TABLE_WATCH_CURSORS",
    "TABLE_WATCH_CURSORS",
    "delete_session_upstream_link",
    "ensure_schema",
    "list_watched_session_upstream_links",
    "read_session_upstream_link",
    "register_session_upstream_watch",
    "update_session_upstream_link_marker",
    "upsert_session_upstream_link",
]
