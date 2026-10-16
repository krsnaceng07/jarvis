"""Best-effort durable signal log for session state changes.

Mirrors OpenClaw's ``src/sessions/session-state-events.ts``.

This is the central event-dispatch surface for session
state changes: a typed-event log backed by a single
SQLite table (``session_state_events``) plus a small
helpers table (``session_state_heads``) and a watcher
table (``session_watch_cursors``).

Public surface (mirrors the TS source):
- ``classify_session_state_actor`` — normalize an actor
  into ``"user" | "operator" | "human" | "system"``
- ``record_session_state_event`` — insert one event
  (with dedupe) and return ``True`` on success
- ``get_session_state_version`` — read the persisted
  state version for a session
- ``get_session_state_versions`` — read all per-session
  state versions
- ``list_session_state_events_since`` — list events
  emitted after a given version
- ``acknowledge_session_state_notices`` — drop delivered
  notice rows
- ``handle_session_state_session_reset`` /
  ``handle_session_state_session_deleted`` — clear state
  for a reset / deleted session
- ``sweep_session_state_watch_notices`` — prune old
  state events + notice markers
- ``register_session_state_watch`` — register a watcher
  for a target session
- ``register_main_session_group_watch`` — bulk-register
  ambient group watches
- ``record_session_human_direct_message`` — convenience
  helper for human-direct-message events
- ``record_subagent_spawned`` /
  ``record_subagent_terminal_state`` — subagent lifecycle
- ``record_session_compacted`` / ``record_session_goal_changed`` —
  lifecycle bookkeeping

Public constants:
- ``SESSION_STATE_RETENTION_MS`` = 30 days
- ``SESSION_STATE_MAX_ROWS`` = 50_000
- ``SESSION_STATE_PRUNE_INTERVAL_MS`` = 1 hour

Re-exports:
- ``SessionStateActorType`` from session_state_event_kinds

Phase 5.18 — "second consumer" of jarvis_state_core:
- ``SessionStateDatabaseOptions`` keeps the public
  ``connection_factory`` / ``env`` / ``path`` / ``now``
  surface (so callers and tests don't change) but
  internally builds a ``jarvis_state_core.StateDatabase``
  that owns the connection lifecycle. The connection
  factory call delegates to ``StateDatabase.open()`` so
  the standard pragmas (busy_timeout, WAL, foreign_keys)
  apply across the runtime + tests.
- ``ensure_schema()`` delegates to
  ``jarvis_state_core.ensure_schema()`` for the canonical
  baseline tables. The combined DDL matches state_core's
  default + the session-events index so a fresh
  ``StateDatabase`` open produces the same shape.

Python adaptations (documented in code):
- TS Kysely query builder → direct ``sqlite3`` SQL. The
  OpenClaw queries compile to a small set of well-known
  ``SELECT`` / ``INSERT … ON CONFLICT`` / ``UPDATE`` /
  ``DELETE`` statements; we keep the SQL explicit.
- TS ``DatabaseSync`` (node:sqlite) → Python
  ``sqlite3.Connection`` (DB-API 2.0). The connection is
  injected via the ``connection_factory`` option so the
  host can wire the canonical state DB
  (``~/.jarvis/state/jarvis.sqlite``) and tests can use
  a temp file.
- TS ``DatabaseOptions`` → ``SessionStateDatabaseOptions``
  dataclass with the same per-call ``now`` override.
- ``loadSessionEntry`` is injected via the ``load_entry``
  option (production wiring is the responsibility of the
  host when the session-accessor module is ported).
- ``buildAgentMainSessionKey`` /
  ``resolveAgentIdFromSessionKey`` from
  ``routing/session-key.ts`` are inlined as small pure
  helpers (``build_agent_main_session_key`` /
  ``resolve_agent_id_from_session_key``).
- ``SessionWatchCursorProvenance`` is an inlined literal
  union (``"explicit" | "ambient_group"``) with a
  ``PROVENANCE_EXPLICIT`` / ``PROVENANCE_AMBIENT_GROUP``
  module-level constant.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, TypedDict

import jarvis_state_core

from src.sessions.session_state_event_kinds import (
    SessionStateActorType,
    SessionStateEventKind,
)
from src.sessions.session_state_notices import (
    enqueue_session_state_notice,
    is_notifiable_watcher_key,
)

logger = logging.getLogger("jarvis.sessions.state_events")

# Re-export the public type so callers can import it from
# this module (mirrors the TS export block).
__all__ = [
    "SESSION_STATE_MAX_ROWS",
    "SESSION_STATE_PRUNE_INTERVAL_MS",
    "SESSION_STATE_RETENTION_MS",
    "SessionStateActorType",
    "SessionStateDatabaseOptions",
    "SessionStateEventInput",
    "SessionStateEventRecord",
    "acknowledge_session_state_notices",
    "classify_session_state_actor",
    "get_session_state_version",
    "get_session_state_versions",
    "handle_session_state_session_deleted",
    "handle_session_state_session_reset",
    "list_ambient_group_watch_targets",
    "list_session_state_events_since",
    "record_session_compacted",
    "record_session_goal_changed",
    "record_session_human_direct_message",
    "record_session_state_event",
    "record_subagent_spawned",
    "record_subagent_terminal_state",
    "register_main_session_group_watch",
    "register_session_state_watch",
    "sweep_session_state_watch_notices",
]

# Public constants (mirrors the TS source).
SESSION_STATE_RETENTION_MS = 30 * 24 * 60 * 60_000  # 30 days
SESSION_STATE_MAX_ROWS = 50_000
SESSION_STATE_PRUNE_INTERVAL_MS = 60 * 60_000  # 1 hour

# Inlined SessionWatchCursorProvenance literal union
# (mirrors ``../state/session-watch-cursor-provenance.ts``).
SessionWatchCursorProvenance = Literal["explicit", "ambient_group"]
SESSION_WATCH_PROVENANCE_EXPLICIT: SessionWatchCursorProvenance = "explicit"
SESSION_WATCH_PROVENANCE_AMBIENT_GROUP: SessionWatchCursorProvenance = (
    "ambient_group"
)
VALID_SESSION_WATCH_PROVENANCES: frozenset[str] = frozenset(
    {"explicit", "ambient_group"}
)


# ── Table + schema bootstrap ──────────────────────────────


TABLE_STATE_EVENTS = "session_state_events"
TABLE_STATE_HEADS = "session_state_heads"
TABLE_WATCH_CURSORS = "session_watch_cursors"


SCHEMA_STATE_EVENTS = """
CREATE TABLE IF NOT EXISTS session_state_events (
    sequence        INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key     TEXT    NOT NULL,
    session_id      TEXT,
    agent_id        TEXT    NOT NULL,
    kind            TEXT    NOT NULL,
    actor_type      TEXT    NOT NULL,
    actor_id        TEXT,
    run_id          TEXT,
    dedupe_key      TEXT,
    occurred_at     INTEGER NOT NULL,
    recorded_at     INTEGER NOT NULL,
    summary         TEXT    NOT NULL,
    payload_json    TEXT
)
""".strip()

SCHEMA_STATE_HEADS = """
CREATE TABLE IF NOT EXISTS session_state_heads (
    session_key TEXT PRIMARY KEY,
    version     INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
)
""".strip()

SCHEMA_WATCH_CURSORS = """
CREATE TABLE IF NOT EXISTS session_watch_cursors (
    target_session_key TEXT NOT NULL,
    watcher_session_key TEXT NOT NULL,
    provenance         TEXT NOT NULL,
    last_delivered_at  INTEGER,
    created_at         INTEGER NOT NULL,
    PRIMARY KEY (target_session_key, watcher_session_key)
)
""".strip()


SCHEMA_STATE_EVENTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_session_state_events_session "
    "ON session_state_events (session_key, sequence)"
)


# ── Types ──────────────────────────────────────────────────


class SessionStateEventInput(TypedDict, total=False):
    sessionKey: str
    sessionId: str
    agentId: str
    kind: SessionStateEventKind
    actorType: SessionStateActorType
    actorId: str
    runId: str
    dedupeKey: str
    summary: str
    payload: dict[str, Any]
    occurredAt: int
    watcherSessionKeys: list[str]


class SessionStateEventRecord(TypedDict, total=False):
    sequence: int
    sessionKey: str
    sessionId: str
    agentId: str
    kind: SessionStateEventKind
    actorType: SessionStateActorType
    actorId: str
    runId: str
    occurredAt: int
    summary: str
    payload: dict[str, Any]


@dataclass
class SessionStateDatabaseOptions:
    """Connection-factory + override bag for the state-event helpers.

    Mirrors the OpenClaw ``OpenClawStateDatabaseOptions`` plus
    the per-call ``now`` override. The factory is called
    fresh per open so callers can use a per-test temp DB
    or the canonical state DB.

    Phase 5.18 — second consumer of ``jarvis_state_core``:
    the dataclass still carries the public
    ``connection_factory`` / ``env`` / ``path`` / ``now``
    surface, but the actual connection lifecycle is owned
    by a lazily-built ``jarvis_state_core.StateDatabase``.
    Public callers don't need to change; the standard
    pragmas (busy_timeout, WAL, foreign_keys) apply
    transparently.
    """

    connection_factory: Optional[Callable[[], sqlite3.Connection]] = None
    env: Optional[dict[str, str]] = None
    path: Optional[str] = None
    now: Optional[int] = None
    load_entry: Optional[Callable[..., Optional[dict[str, Any]]]] = None
    skip_schema_ensure: bool = False
    # Cached StateDatabase. Built lazily on first ``open()``
    # so the dataclass is still cheap to instantiate (tests
    # pass options with no real DB; the StateDatabase is
    # only created when the helper actually opens a
    # connection). ``field(default=None, ...)`` is required
    # because dataclass fields with defaults must come
    # after fields without defaults — we put it last via
    # the ``field(default=None, ...)`` marker.
    _state_db_cache: Optional["jarvis_state_core.StateDatabase"] = field(
        default=None,
        repr=False,
        compare=False,
    )


@dataclass
class _PruneState:
    last_prune_at: int = 0


_PRUNE = _PruneState()


# ── DB helpers ─────────────────────────────────────────────


def _build_state_db(
    options: SessionStateDatabaseOptions,
) -> "jarvis_state_core.StateDatabase":
    """Lazily build a ``StateDatabase`` for ``options``.

    Mirrors OpenClaw's ``openOpenClawStateDatabase``: the
    options bag carries the public input shape, and the
    state database handle is the single source of truth
    for the connection lifecycle. The cache lives on
    ``options._state_db_cache`` so repeated calls reuse
    the same per-store-path queue map.
    """
    if options._state_db_cache is not None:
        return options._state_db_cache
    if options.connection_factory is None:
        raise ValueError(
            "session_state_events: connection_factory is required "
            "(host must wire the canonical state DB)"
        )
    state_options = jarvis_state_core.StateDatabaseOptions(
        connection_factory=options.connection_factory,
        env=options.env,
        path=options.path,
        now=options.now,
    )
    options._state_db_cache = jarvis_state_core.StateDatabase(state_options)
    return options._state_db_cache


def _open(options: SessionStateDatabaseOptions) -> sqlite3.Connection:
    """Open a fresh connection via the cached ``StateDatabase``.

    Mirrors ``openOpenClawStateDatabase`` followed by
    ``conn`` access: the OpenClaw handle returns
    ``{db, path, walMaintenance}`` and the helper uses
    ``db`` directly. The Python port uses
    ``StateDatabase.open()`` which returns a
    ``sqlite3.Connection`` with the standard pragmas
    already applied (busy_timeout, WAL, foreign_keys).
    """
    return _build_state_db(options).open()


# Combined DDL is provided by ``jarvis_state_core.ensure_schema``'s
# default (the canonical baseline covers every table the
# sessions helpers touch, including the per-module
# ``idx_session_state_events_session`` index). The sessions
# modules just delegate to state_core's ensure_schema with no
# ``schema_sql`` override so the runtime + tests share the
# same baseline DDL.


def ensure_schema(options: SessionStateDatabaseOptions) -> None:
    """Create the canonical state-event tables if missing.

    Mirrors the OpenClaw ``ensureSessionStateSchema``
    flow. The Python port delegates to
    ``jarvis_state_core.ensure_schema`` so the runtime
    + tests share the same baseline DDL (and the
    per-module ``idx_session_state_events_session``
    index, which state_core's default already creates).
    """
    conn = _open(options)
    try:
        jarvis_state_core.ensure_schema(conn)
    finally:
        conn.close()


def _ensure_schema_for_options(options: SessionStateDatabaseOptions) -> None:
    if options.skip_schema_ensure or options.connection_factory is None:
        return
    ensure_schema(options)


# ── Number / payload helpers ──────────────────────────────


def _normalize_sqlite_number(
    value: Any,
) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return int(float(value))
            except ValueError:
                return None
    return None


def _parse_payload(value: Optional[str]) -> Optional[dict[str, Any]]:
    """Parse a payload column to a JSON object, or ``None``.

    Mirrors the private ``parsePayload`` helper.
    """
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    if isinstance(parsed, dict) and not isinstance(parsed, list):
        return parsed
    return None


def _row_to_event(row: sqlite3.Row) -> SessionStateEventRecord:
    """Map a ``session_state_events`` row to the public dict shape."""
    payload = _parse_payload(row["payload_json"])
    record: SessionStateEventRecord = {
        "sequence": int(row["sequence"]),
        "sessionKey": row["session_key"],
        "agentId": row["agent_id"],
        "kind": row["kind"],
        "actorType": row["actor_type"],
        "occurredAt": int(row["occurred_at"]),
        "summary": row["summary"],
    }
    if row["session_id"] is not None:
        record["sessionId"] = row["session_id"]
    if row["actor_id"] is not None:
        record["actorId"] = row["actor_id"]
    if row["run_id"] is not None:
        record["runId"] = row["run_id"]
    if payload is not None:
        record["payload"] = payload
    return record


# ── Inlined routing helpers ────────────────────────────────


def build_agent_main_session_key(
    agent_id: str, main_key: Optional[str] = None
) -> str:
    """Build the canonical ``agent:<id>:<mainKey>`` session key.

    Mirrors ``buildAgentMainSessionKey`` from
    ``routing/session-key.ts``. ``mainKey`` defaults to
    ``"main"``.
    """
    normalized_main_key = (main_key or "main").strip() or "main"
    return f"agent:{agent_id}:{normalized_main_key}"


def resolve_agent_id_from_session_key(session_key: str) -> Optional[str]:
    """Extract the agent id from a canonical ``agent:<id>:...`` session key.

    Mirrors ``resolveAgentIdFromSessionKey`` from
    ``routing/session-key.ts``. Returns ``None`` for
    non-canonical keys.
    """
    if not session_key or not isinstance(session_key, str):
        return None
    parts = session_key.split(":")
    if len(parts) < 3 or parts[0] != "agent" or not parts[1]:
        return None
    return parts[1]


# ── Public surface ─────────────────────────────────────────


def classify_session_state_actor(
    *,
    actor: Optional[dict[str, Any]] = None,
    actor_type: Optional[str] = None,
) -> SessionStateActorType:
    """Normalize an actor into ``"user" | "operator" | "human" | "system"``.

    Mirrors ``classifySessionStateActor``. The TS version
    accepts an ``actor: { actorType?: ... }`` object OR a
    direct ``actorType`` string; both shapes are
    supported.
    """
    candidate: Optional[str] = actor_type
    if candidate is None and isinstance(actor, dict):
        candidate = actor.get("actorType") or actor.get("actor_type")
    if not isinstance(candidate, str):
        return "system"
    lowered = candidate.strip().lower()
    if lowered in ("user", "operator", "human", "system"):
        return lowered  # type: ignore[return-value]
    return "system"


def record_session_state_event(
    params: SessionStateEventInput,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Insert a state event (with dedupe) and return ``True`` on success.

    Mirrors ``recordSessionStateEvent``. The event is
    fanned out to watcher cursors via
    ``enqueueSessionStateNotice`` after the insert
    succeeds.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    now = options.now if options.now is not None else int(time.time() * 1000)
    occurred_at = (
        int(params.get("occurredAt"))
        if isinstance(params.get("occurredAt"), (int, float))
        else now
    )
    payload = params.get("payload")
    payload_json = json.dumps(payload) if payload else None
    actor_type = classify_session_state_actor(
        actor_type=params.get("actorType"),
    )
    try:
        with _open(options) as conn:
            # Dedupe: if a row with the same dedupe_key
            # already exists for this session, drop the
            # insert.
            dedupe_key = params.get("dedupeKey")
            if dedupe_key:
                existing = conn.execute(
                    f"SELECT sequence FROM {TABLE_STATE_EVENTS} "
                    "WHERE session_key = ? AND dedupe_key = ?",
                    (params.get("sessionKey", ""), dedupe_key),
                ).fetchone()
                if existing is not None:
                    return False
            cursor = conn.execute(
                f"""
                INSERT INTO {TABLE_STATE_EVENTS} (
                    session_key, session_id, agent_id, kind,
                    actor_type, actor_id, run_id, dedupe_key,
                    occurred_at, recorded_at, summary, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    params.get("sessionKey", ""),
                    params.get("sessionId"),
                    params.get("agentId", ""),
                    params.get("kind", ""),
                    actor_type,
                    params.get("actorId"),
                    params.get("runId"),
                    dedupe_key,
                    occurred_at,
                    now,
                    params.get("summary", ""),
                    payload_json,
                ),
            )
            sequence = int(cursor.lastrowid or 0)
            # Update the session head: version = max(version, sequence).
            conn.execute(
                f"""
                INSERT INTO {TABLE_STATE_HEADS} (session_key, version, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (session_key) DO UPDATE SET
                    version = MAX(version, excluded.version),
                    updated_at = excluded.updated_at
                """,
                (params.get("sessionKey", ""), sequence, now),
            )
            conn.commit()
        # Fan out to watchers.
        watchers = _list_watcher_keys(
            options, params.get("sessionKey", ""), now
        )
        for watcher_key in watchers:
            enqueue_session_state_notice(
                {
                    "watcherSessionKey": watcher_key,
                    "targetSessionKey": params.get("sessionKey", ""),
                    "lastSeenSequence": sequence,
                }
            )
        return True
    except sqlite3.Error as error:
        logger.warning("failed to record session state event: %s", error)
        return False


def _list_watcher_keys(
    options: SessionStateDatabaseOptions,
    session_key: str,
    now: int,
) -> list[str]:
    """Return the watcher session keys for a target session.

    Mirrors the private watcher-key resolver. Excludes
    keys that are not notifiable per
    ``isNotifiableWatcherKey``.
    """
    try:
        with _open(options) as conn:
            rows = conn.execute(
                f"SELECT watcher_session_key FROM {TABLE_WATCH_CURSORS} "
                "WHERE target_session_key = ?",
                (session_key,),
            ).fetchall()
        keys = [row["watcher_session_key"] for row in rows]
        return [k for k in keys if is_notifiable_watcher_key(k)]
    except sqlite3.Error:
        return []


def get_session_state_version(
    session_key: str,
    agent_id: str,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> int:
    """Read the persisted state version for one session.

    Mirrors ``getSessionStateVersion``. Returns 0 when the
    session has no recorded state yet.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    try:
        with _open(options) as conn:
            row = conn.execute(
                f"SELECT version FROM {TABLE_STATE_HEADS} "
                "WHERE session_key = ?",
                (session_key,),
            ).fetchone()
        return int(row["version"]) if row else 0
    except sqlite3.Error as error:
        logger.warning("failed to read session state version: %s", error)
        return 0


def get_session_state_versions(
    options: Optional[SessionStateDatabaseOptions] = None,
) -> dict[str, int]:
    """Read all per-session state versions.

    Mirrors ``getSessionStateVersions``. Returns a
    ``{session_key: version}`` dict.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    try:
        with _open(options) as conn:
            rows = conn.execute(
                f"SELECT session_key, version FROM {TABLE_STATE_HEADS}"
            ).fetchall()
        return {row["session_key"]: int(row["version"]) for row in rows}
    except sqlite3.Error as error:
        logger.warning("failed to read session state versions: %s", error)
        return {}


def list_session_state_events_since(
    session_key: str,
    agent_id: str,
    since_sequence: int,
    limit: int,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> dict[str, Any]:
    """List events for one session emitted after ``since_sequence``.

    Mirrors ``listSessionStateEventsSince``. Returns
    ``{"events": [...], "version": <int>}``.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    version = get_session_state_version(session_key, agent_id, options)
    if since_sequence >= version:
        return {"events": [], "version": version}
    try:
        with _open(options) as conn:
            rows = conn.execute(
                f"SELECT * FROM {TABLE_STATE_EVENTS} "
                "WHERE session_key = ? AND sequence > ? "
                "ORDER BY sequence ASC LIMIT ?",
                (session_key, int(since_sequence), int(limit)),
            ).fetchall()
        return {
            "events": [_row_to_event(row) for row in rows],
            "version": version,
        }
    except sqlite3.Error as error:
        logger.warning("failed to list session state events: %s", error)
        return {"events": [], "version": version}


def acknowledge_session_state_notices(
    session_key: str,
    agent_id: str,
    watcher_session_key: str,
    through_sequence: int,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Drop delivered notice rows up to ``through_sequence``.

    Mirrors ``acknowledgeSessionStateNotices``. Returns
    ``True`` when a row was updated.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    now = options.now if options.now is not None else int(time.time() * 1000)
    try:
        with _open(options) as conn:
            cursor = conn.execute(
                f"UPDATE {TABLE_WATCH_CURSORS} "
                "SET last_delivered_at = ? "
                "WHERE target_session_key = ? AND watcher_session_key = ? "
                "AND (last_delivered_at IS NULL OR last_delivered_at < ?)",
                (now, session_key, watcher_session_key, int(through_sequence)),
            )
            conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as error:
        logger.warning("failed to acknowledge session state notice: %s", error)
        return False


def handle_session_state_session_reset(
    session_key: str,
    agent_id: str,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> None:
    """Clear state for a reset session.

    Mirrors ``handleSessionStateSessionReset``. Deletes
    events, head, and watch-cursor rows for the session.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    try:
        with _open(options) as conn:
            conn.execute(
                f"DELETE FROM {TABLE_STATE_EVENTS} WHERE session_key = ?",
                (session_key,),
            )
            conn.execute(
                f"DELETE FROM {TABLE_STATE_HEADS} WHERE session_key = ?",
                (session_key,),
            )
            conn.execute(
                f"DELETE FROM {TABLE_WATCH_CURSORS} "
                "WHERE target_session_key = ? OR watcher_session_key = ?",
                (session_key, session_key),
            )
            conn.commit()
    except sqlite3.Error as error:
        logger.warning("failed to reset session state: %s", error)


handle_session_state_session_deleted = handle_session_state_session_reset


def sweep_session_state_watch_notices(
    options: Optional[SessionStateDatabaseOptions] = None,
) -> int:
    """Prune old state events + notice markers.

    Mirrors ``sweepSessionStateWatchNotices``. Returns the
    number of rows pruned.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    now = options.now if options.now is not None else int(time.time() * 1000)
    if (
        _PRUNE.last_prune_at
        and now - _PRUNE.last_prune_at < SESSION_STATE_PRUNE_INTERVAL_MS
    ):
        return 0
    _PRUNE.last_prune_at = now
    cutoff = now - SESSION_STATE_RETENTION_MS
    try:
        with _open(options) as conn:
            # Drop events older than the retention window.
            cursor = conn.execute(
                f"DELETE FROM {TABLE_STATE_EVENTS} "
                "WHERE occurred_at < ?",
                (cutoff,),
            )
            events_pruned = cursor.rowcount
            # Cap the table size to SESSION_STATE_MAX_ROWS by
            # dropping the oldest rows first.
            count_row = conn.execute(
                f"SELECT COUNT(*) AS n FROM {TABLE_STATE_EVENTS}"
            ).fetchone()
            count = int(count_row["n"]) if count_row else 0
            excess = max(0, count - SESSION_STATE_MAX_ROWS)
            if excess > 0:
                cursor = conn.execute(
                    f"DELETE FROM {TABLE_STATE_EVENTS} "
                    "WHERE sequence IN ("
                    f"  SELECT sequence FROM {TABLE_STATE_EVENTS} "
                    f"  ORDER BY sequence ASC LIMIT ?"
                    ")",
                    (excess,),
                )
                events_pruned += cursor.rowcount
            conn.commit()
        return events_pruned
    except sqlite3.Error as error:
        logger.warning("failed to sweep session state notices: %s", error)
        return 0


def record_session_compacted(
    *,
    session_key: str,
    agent_id: str,
    summary: str = "session compacted",
    payload: Optional[dict[str, Any]] = None,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Record a ``compaction`` event. Mirrors ``recordSessionCompacted``."""
    return record_session_state_event(
        {
            "sessionKey": session_key,
            "agentId": agent_id,
            "kind": "compaction",
            "actorType": "system",
            "summary": summary,
            **({"payload": payload} if payload else {}),
        },
        options,
    )


def record_session_goal_changed(
    *,
    session_key: str,
    agent_id: str,
    summary: str = "session goal changed",
    payload: Optional[dict[str, Any]] = None,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Record a ``goal_changed`` event. Mirrors ``recordSessionGoalChanged``."""
    return record_session_state_event(
        {
            "sessionKey": session_key,
            "agentId": agent_id,
            "kind": "goal_changed",
            "actorType": "system",
            "summary": summary,
            **({"payload": payload} if payload else {}),
        },
        options,
    )


def list_ambient_group_watch_targets(
    options: Optional[SessionStateDatabaseOptions] = None,
) -> list[str]:
    """List the session keys that have an ambient-group watch registered.

    Mirrors ``listAmbientGroupWatchTargets``. Returns the
    distinct target_session_key values whose provenance
    is ``ambient_group``.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    try:
        with _open(options) as conn:
            rows = conn.execute(
                f"SELECT DISTINCT target_session_key FROM {TABLE_WATCH_CURSORS} "
                "WHERE provenance = ?",
                (SESSION_WATCH_PROVENANCE_AMBIENT_GROUP,),
            ).fetchall()
        return [row["target_session_key"] for row in rows]
    except sqlite3.Error as error:
        logger.warning("failed to list ambient group watch targets: %s", error)
        return []


def register_session_state_watch(
    *,
    watcher_session_key: str,
    target_session_key: str,
    provenance: SessionWatchCursorProvenance = SESSION_WATCH_PROVENANCE_EXPLICIT,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Register a watcher for a target session.

    Mirrors ``registerSessionStateWatch``. Returns
    ``True`` on success, ``False`` when the cursor was
    rejected.
    """
    options = options or SessionStateDatabaseOptions()
    _ensure_schema_for_options(options)
    if not is_notifiable_watcher_key(watcher_session_key):
        return False
    if watcher_session_key == target_session_key:
        return False
    if provenance not in VALID_SESSION_WATCH_PROVENANCES:
        return False
    now = options.now if options.now is not None else int(time.time() * 1000)
    try:
        with _open(options) as conn:
            conn.execute(
                f"INSERT INTO {TABLE_WATCH_CURSORS} ("
                "target_session_key, watcher_session_key, provenance, "
                "last_delivered_at, created_at"
                ") VALUES (?, ?, ?, NULL, ?) "
                "ON CONFLICT (target_session_key, watcher_session_key) "
                "DO UPDATE SET provenance = excluded.provenance",
                (target_session_key, watcher_session_key, provenance, now),
            )
            conn.commit()
        return True
    except sqlite3.Error as error:
        logger.warning("failed to register session state watch: %s", error)
        return False


def register_main_session_group_watch(
    *,
    agent_id: str,
    targets: list[str],
    options: Optional[SessionStateDatabaseOptions] = None,
) -> int:
    """Bulk-register ambient group watches for an agent.

    Mirrors ``registerMainSessionGroupWatch``. Returns the
    number of registrations accepted.
    """
    options = options or SessionStateDatabaseOptions()
    watcher_key = build_agent_main_session_key(agent_id)
    accepted = 0
    for target in targets:
        if register_session_state_watch(
            watcher_session_key=watcher_key,
            target_session_key=target,
            provenance=SESSION_WATCH_PROVENANCE_AMBIENT_GROUP,
            options=options,
        ):
            accepted += 1
    return accepted


def record_session_human_direct_message(
    params: dict[str, Any],
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Record a ``human_direct_message`` event.

    Mirrors ``recordSessionHumanDirectMessage``. Clamps
    ``occurredAt`` into ``[now - 24h, now]`` so a skewed
    upstream timestamp cannot age watch state into
    retention pruning.
    """
    options = options or SessionStateDatabaseOptions()
    now = options.now if options.now is not None else int(time.time() * 1000)
    occurred_at = params.get("occurredAt")
    if not isinstance(occurred_at, (int, float)):
        occurred_at = now
    occurred_at = max(now - 24 * 60 * 60_000, min(int(occurred_at), now))
    actor = params.get("actor")
    actor_type = classify_session_state_actor(actor=actor)
    payload = params.get("payload")
    return record_session_state_event(
        {
            "sessionKey": params.get("sessionKey", ""),
            "agentId": params.get("agentId", ""),
            "kind": "human_direct_message",
            "actorType": actor_type,
            "dedupeKey": params.get("dedupeKey"),
            "summary": f"human message via {params.get('channel', '')}".strip(),
            "occurredAt": int(occurred_at),
            **({"payload": payload} if payload else {}),
        },
        options,
    )


def record_subagent_spawned(
    *,
    session_key: str,
    agent_id: str,
    subagent_id: str,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Record a ``subagent_spawned`` event. Mirrors ``recordSubagentSpawned``."""
    return record_session_state_event(
        {
            "sessionKey": session_key,
            "agentId": agent_id,
            "kind": "subagent_spawned",
            "actorType": "system",
            "summary": f"subagent {subagent_id} spawned",
            "payload": {"subagentId": subagent_id},
        },
        options,
    )


def record_subagent_terminal_state(
    *,
    session_key: str,
    agent_id: str,
    subagent_id: str,
    terminal: str,
    options: Optional[SessionStateDatabaseOptions] = None,
) -> bool:
    """Record a ``subagent_terminated`` event.

    Mirrors ``recordSubagentTerminalState``.
    """
    return record_session_state_event(
        {
            "sessionKey": session_key,
            "agentId": agent_id,
            "kind": "subagent_terminated",
            "actorType": "system",
            "summary": f"subagent {subagent_id} {terminal}",
            "payload": {"subagentId": subagent_id, "terminal": terminal},
        },
        options,
    )
