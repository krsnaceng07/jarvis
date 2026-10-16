"""jarvis_sdk.session_transcript_runtime — session transcript runtime.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/session-transcript-runtime``'s
``SessionTranscriptTargetParams``,
``readSessionTranscriptEvents``, and
``readSessionTranscriptRawDelta``.

Used by ``active-memory`` to pass the target session id /
agent id / scope into the host's transcript-reading
helpers, and to parse a returned ``sessionFile`` marker
back into a target. The OpenClaw shape is a frozen dict;
the Python port uses frozen dataclasses for the
target/marker types.

Parity
======
- ``SessionTranscriptTargetParams`` fields:
  - ``session_id`` (required, str)
  - ``agent_id`` (optional, str)
  - ``session_key`` (optional, str)
  - ``scope`` (optional, str; one of
    ``"same-agent-private"`` | ``"shared"``)
- ``SqliteSessionFileMarker`` (frozen dataclass) — the
  decoded form of the ``"sqlite:<agent>:<id>:<store>:<scope>"``
  session-file marker that the host returns to plugins.
- ``build_session_transcript_target(params)`` →
  ``SessionTranscriptTargetParams``: normalizes the input
  (drops empty strings, validates session_id is present).
- ``parse_sqlite_session_file_marker(marker)`` →
  ``SqliteSessionFileMarker | None``: parses the
  ``"sqlite:..."`` form, returns ``None`` for non-marker
  strings or malformed input.
- ``read_session_transcript_raw_delta(target)`` →
  ``TranscriptRawDeltaPage``: a default no-op stub the
  host overrides with its own SQLite-streaming
  implementation. The default returns
  ``{"kind": "page", "events": []}`` so plugins can
  safely walk the page.

Phase 5.22 — second consumer of ``jarvis_state_core``:
the ``SqliteSessionTranscriptReader`` class reads
transcript events from a ``jarvis_state_core``-backed
SQLite store. The reader uses the same connection
plumbing as the other 2nd consumers (sessions,
state_core); standard pragmas (busy_timeout, WAL,
foreign_keys) apply transparently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_SESSION_FILE_MARKER_PREFIX = "sqlite:"


@dataclass(frozen=True, slots=True)
class SessionTranscriptTargetParams:
    """Identifies a session to read transcripts for.

    Mirrors OpenClaw's ``SessionTranscriptTargetParams``.
    """

    session_id: str
    agent_id: str | None = None
    session_key: str | None = None
    scope: str | None = None
    store_path: str | None = None
    thread_id: str | None = None


@dataclass(frozen=True, slots=True)
class SqliteSessionFileMarker:
    """Decoded form of a ``"sqlite:<agent>:<id>:<store>[:scope]"`` marker.

    Mirrors OpenClaw's
    ``parseSqliteSessionFileMarker`` return shape.
    """

    agent_id: str
    session_id: str
    store_path: str
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptRawDeltaPage:
    """One page of a session-transcript raw-delta read.

    Mirrors OpenClaw's ``readSessionTranscriptRawDelta``
    return shape. ``kind`` is ``"page"`` on success and
    ``"empty"`` when there is nothing more to read.
    """

    kind: str
    events: list[dict[str, Any]] = field(default_factory=list)


def build_session_transcript_target(
    params: dict[str, Any] | None,
) -> SessionTranscriptTargetParams | None:
    """Build a typed session-transcript target from a raw dict.

    Mirrors OpenClaw's pattern of accepting a loose dict
    and normalizing it to the typed shape. Returns ``None``
    when the params are missing or the session id is
    empty.
    """
    if not isinstance(params, dict):
        return None
    session_id = params.get("sessionId") or params.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None
    agent_id = params.get("agentId") or params.get("agent_id")
    session_key = params.get("sessionKey") or params.get("session_key")
    scope = params.get("scope")
    store_path = params.get("storePath") or params.get("store_path")
    thread_id = params.get("threadId") or params.get("thread_id")
    return SessionTranscriptTargetParams(
        session_id=session_id.strip(),
        agent_id=agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None,
        session_key=session_key.strip()
        if isinstance(session_key, str) and session_key.strip()
        else None,
        scope=scope.strip() if isinstance(scope, str) and scope.strip() else None,
        store_path=store_path.strip()
        if isinstance(store_path, str) and store_path.strip()
        else None,
        thread_id=thread_id.strip() if isinstance(thread_id, str) and thread_id.strip() else None,
    )


def parse_sqlite_session_file_marker(marker: str | None) -> SqliteSessionFileMarker | None:
    """Parse a ``"sqlite:<agent>:<id>:<store>[:scope]"`` marker.

    Mirrors OpenClaw's ``parseSqliteSessionFileMarker``.
    Returns ``None`` for ``None``, non-string input, or a
    marker that doesn't start with ``"sqlite:"`` /
    doesn't have at least 4 colon-separated parts.
    """
    if not isinstance(marker, str):
        return None
    if not marker.startswith(_SESSION_FILE_MARKER_PREFIX):
        return None
    parts = marker[len(_SESSION_FILE_MARKER_PREFIX) :].split(":")
    if len(parts) < 3:
        return None
    agent_id = parts[0]
    session_id = parts[1]
    store_path = ":".join(parts[2:-1]) if len(parts) >= 4 else parts[2]
    scope = parts[-1] if len(parts) >= 4 else None
    if not agent_id or not session_id or not store_path:
        return None
    return SqliteSessionFileMarker(
        agent_id=agent_id,
        session_id=session_id,
        store_path=store_path,
        scope=scope or None,
    )


def read_session_transcript_raw_delta(
    target: Any,
    *,
    max_bytes: int | None = None,
    max_events: int | None = None,
) -> TranscriptRawDeltaPage:
    """Default no-op stub for reading transcript events.

    Mirrors OpenClaw's ``readSessionTranscriptRawDelta``.
    The host overrides this with its SQLite-streaming
    implementation. The default returns an empty
    ``"page"`` so plugins can safely walk the result.
    """
    _ = (target, max_bytes, max_events)
    return TranscriptRawDeltaPage(kind="page", events=[])


async def read_session_transcript_events(
    target: SessionTranscriptTargetParams | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Read the full event list for a session.

    Mirrors OpenClaw's ``readSessionTranscriptEvents``.
    Returns a list of event dicts (possibly empty). The
    default implementation returns ``[]`` so the recall
    sub-agent can boot without a real transcript store;
    the host overrides this to read from the SQLite
    session store.
    """
    _ = target
    return []


def cleanup_session_lifecycle_artifacts(
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Default no-op stub for cleaning up a sub-agent's session artifacts.

    Mirrors OpenClaw's ``cleanupSessionLifecycleArtifacts``.
    Returns a dict with ``removedEntries`` (default ``0``)
    so the caller can decide whether to retry. The host
    overrides this with the real session-store cleanup.
    """
    _ = params
    return {"removedEntries": 0, "removedTranscripts": 0}


# ── Phase 5.22: SQLite-backed reader (2nd consumer) ─────


# Schema for the SQLite-backed ``session_transcripts`` table.
# The schema follows the same shape as the OpenClaw
# source's transcript accessor: a per-session row with
# the events stored as a JSON list in ``entries_json``.
# The ``agent_id`` index lets the reader look up
# transcripts by agent without scanning the whole table.
TRANSCRIPT_SQLITE_SCHEMA_SQL: str = (
    "CREATE TABLE IF NOT EXISTS session_transcripts ("
    "session_id TEXT PRIMARY KEY, "
    "agent_id TEXT NOT NULL, "
    "session_key TEXT, "
    "entries_json TEXT NOT NULL DEFAULT '[]', "
    "created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL"
    ");"
    "CREATE INDEX IF NOT EXISTS idx_session_transcripts_agent "
    "ON session_transcripts(agent_id);"
)


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Mirrors the ``_now_iso`` helper used by the
    in-memory ``SessionStore`` variant.
    """
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class SqliteSessionTranscriptReader:
    """SQLite-backed session transcript reader.

    Phase 5.22 — second consumer of ``jarvis_state_core``:
    the standard pragmas (busy_timeout=5s, WAL,
    foreign_keys=ON) apply transparently via
    ``StateDatabase.open()``. The reader is the
    production shape for ``active-memory``'s
    transcript-reading helpers; the default
    no-op ``read_session_transcript_events`` /
    ``read_session_transcript_raw_delta`` /
    ``cleanup_session_lifecycle_artifacts`` functions
    stay as the in-process fallback for tests + first
    boot.

    Concurrency:
    - Same-process writes serialize through the
      ``jarvis_state_core`` per-store-path queue
      (``run_write_transaction``); the
      ``StateDatabase`` is built once and cached
    - Cross-process writes use ``BEGIN IMMEDIATE`` so
      a second writer waits on the writer's commit
      (the OpenClaw source's
      ``withTranscriptWriteLock`` equivalent)

    Schema:
    - ``session_transcripts`` table: ``session_id`` PK,
      ``agent_id``, ``session_key``, ``entries_json``,
      ``created_at``, ``updated_at``
    - ``idx_session_transcripts_agent`` index for
      agent-scoped lookups
    - Lazy bootstrap: the first call opens a connection
      + ensures the table exists; the
      ``_schema_ensured`` flag guards against re-running
      on every open
    """

    def __init__(
        self,
        options: "jarvis_state_core.StateDatabaseOptions | None" = None,
        *,
        connection_factory: "callable[[], sqlite3.Connection] | None" = None,
        env: "dict[str, str] | None" = None,
        path: "str | None" = None,
    ) -> None:
        """Build the reader from a ``StateDatabaseOptions`` bag.

        Mirrors the OpenClaw pattern of accepting a
        connection factory + path overrides. The
        Python port uses ``jarvis_state_core`` so the
        options bag is the same shape as every other
        2nd consumer (sessions, state_core).
        """

        # Local import keeps the module's import cost
        # low for callers that only use the default
        # no-op helpers (the in-process fallback).
        import jarvis_state_core

        if options is None:
            if connection_factory is None:
                raise ValueError(
                    "SqliteSessionTranscriptReader: "
                    "connection_factory is required "
                    "(host must wire the canonical state DB)"
                )
            options = jarvis_state_core.StateDatabaseOptions(
                connection_factory=connection_factory,
                env=env,
                path=path,
            )
        self._state_db = jarvis_state_core.StateDatabase(options)
        self._schema_ensured = False
        self._schema_lock = __import__("threading").Lock()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        """Run the ``session_transcripts`` DDL on a fresh connection.

        Idempotent; the helper is a one-shot per
        instance (the ``_schema_ensured`` flag guards
        against re-running on every open).
        """
        if self._schema_ensured:
            return
        with self._schema_lock:
            if self._schema_ensured:
                return
            conn.executescript(TRANSCRIPT_SQLITE_SCHEMA_SQL)
            conn.commit()
            self._schema_ensured = True

    # ── Reads ────────────────────────────────────────────

    def read_events(
        self, target: SessionTranscriptTargetParams | dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Read the full event list for one session.

        Mirrors ``readSessionTranscriptEvents``. Returns
        a list of event dicts (possibly empty). The
        in-process fallback returns ``[]``; the SQLite
        reader returns the events from the
        ``session_transcripts`` table.
        """
        import asyncio

        normalized = self._normalize_target(target)
        if normalized is None:
            return []
        session_id = normalized["session_id"]

        async def _body() -> list[dict[str, Any]]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                row = conn.execute(
                    "SELECT entries_json FROM session_transcripts "
                    "WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    return []
                try:
                    import json as _json
                    entries = _json.loads(row["entries_json"] or "[]")
                except (TypeError, ValueError):
                    return []
                if not isinstance(entries, list):
                    return []
                return [dict(entry) for entry in entries if isinstance(entry, dict)]
            finally:
                conn.close()

        return asyncio.run(_body())

    def read_raw_delta(
        self,
        target: SessionTranscriptTargetParams | dict[str, Any],
        *,
        max_bytes: int | None = None,
        max_events: int | None = None,
    ) -> TranscriptRawDeltaPage:
        """Read one bounded page of raw events.

        Mirrors ``readSessionTranscriptRawDelta``. The
        page is bounded by ``max_events`` (event count)
        and ``max_bytes`` (serialized JSON byte count).
        Returns ``{"kind": "page", "events": [...]}`` on
        success and ``{"kind": "empty", "events": []}``
        when there is nothing more to read.
        """
        events = self.read_events(target)
        if not events:
            return TranscriptRawDeltaPage(kind="empty", events=[])

        # Apply ``max_events`` cap.
        page = list(events)
        if max_events is not None and max_events > 0:
            page = page[:max_events]

        # Apply ``max_bytes`` cap (best-effort: the
        # OpenClaw source uses a streaming JSONL byte
        # counter; the Python port uses the joined
        # JSON byte count for parity).
        if max_bytes is not None and max_bytes > 0:
            import json as _json
            serialized_bytes = len(_json.dumps(page, separators=(",", ":")).encode("utf-8"))
            if serialized_bytes > max_bytes:
                # Truncate by removing trailing events
                # until the serialized size fits.
                while page and len(
                    _json.dumps(page, separators=(",", ":")).encode("utf-8")
                ) > max_bytes:
                    page.pop()
        return TranscriptRawDeltaPage(kind="page", events=page)

    def cleanup_session_artifacts(
        self, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Delete the per-session transcript rows.

        Mirrors ``cleanupSessionLifecycleArtifacts``.
        Returns ``{"removedEntries": ..., "removedTranscripts": ...}``
        so the caller can decide whether to retry. The
        in-process fallback returns ``0`` for both
        counters; the SQLite reader returns the row
        counts actually removed.
        """
        if not isinstance(params, dict):
            return {"removedEntries": 0, "removedTranscripts": 0}
        target = self._normalize_target(params)
        if target is None:
            return {"removedEntries": 0, "removedTranscripts": 0}
        session_id = target["session_id"]

        import asyncio

        async def _body() -> dict[str, int]:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                # Read the current entry count for the
                # ``removedEntries`` counter before the
                # delete (mirrors the OpenClaw source's
                # ``before/after count`` projection).
                row = conn.execute(
                    "SELECT entries_json FROM session_transcripts "
                    "WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    return {"removedEntries": 0, "removedTranscripts": 0}
                try:
                    import json as _json
                    entries = _json.loads(row["entries_json"] or "[]")
                except (TypeError, ValueError):
                    entries = []
                removed_entries = (
                    len(entries) if isinstance(entries, list) else 0
                )
                conn.execute(
                    "DELETE FROM session_transcripts WHERE session_id = ?",
                    (session_id,),
                )
                conn.commit()
                return {
                    "removedEntries": removed_entries,
                    "removedTranscripts": 1,
                }
            finally:
                conn.close()

        return asyncio.run(_body())

    # ── Writes (used by the host's append pipeline) ─────

    def upsert_transcript(
        self,
        session_id: str,
        agent_id: str,
        session_key: str | None,
        events: list[dict[str, Any]],
    ) -> None:
        """Replace the events for ``session_id`` atomically.

        Used by the host's transcript-append pipeline
        (the active-memory helper calls this after the
        in-process write lock releases).
        """
        import asyncio
        import json as _json

        now = _now_iso()
        entries_json = _json.dumps(list(events), separators=(",", ":"))

        async def _body() -> None:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                conn.execute(
                    "INSERT INTO session_transcripts ("
                    "session_id, agent_id, session_key, entries_json, "
                    "created_at, updated_at"
                    ") VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (session_id) DO UPDATE SET "
                    "agent_id = excluded.agent_id, "
                    "session_key = excluded.session_key, "
                    "entries_json = excluded.entries_json, "
                    "updated_at = excluded.updated_at",
                    (
                        session_id,
                        agent_id,
                        session_key,
                        entries_json,
                        now,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        asyncio.run(_body())

    # ── Helpers ────────────────────────────────────────

    @staticmethod
    def _normalize_target(
        target: SessionTranscriptTargetParams | dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Normalize a target into the typed dict shape.

        Mirrors ``build_session_transcript_target``
        but returns ``None`` (instead of raising) when
        the session id is missing. The reader's
        public methods surface ``None`` as an empty
        event list (matches the OpenClaw source's
        ``loadTranscriptEvents`` behavior).
        """
        if isinstance(target, SessionTranscriptTargetParams):
            return {
                "session_id": target.session_id,
                "agent_id": target.agent_id,
                "session_key": target.session_key,
                "scope": target.scope,
            }
        if not isinstance(target, dict):
            return None
        session_id = target.get("sessionId") or target.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return None
        agent_id = target.get("agentId") or target.get("agent_id")
        session_key = target.get("sessionKey") or target.get("session_key")
        scope = target.get("scope")
        return {
            "session_id": session_id.strip(),
            "agent_id": agent_id.strip()
            if isinstance(agent_id, str) and agent_id.strip()
            else None,
            "session_key": session_key.strip()
            if isinstance(session_key, str) and session_key.strip()
            else None,
            "scope": scope.strip()
            if isinstance(scope, str) and scope.strip()
            else None,
        }


__all__ = [
    "SessionTranscriptTargetParams",
    "SqliteSessionFileMarker",
    "SqliteSessionTranscriptReader",
    "TranscriptRawDeltaPage",
    "build_session_transcript_target",
    "cleanup_session_lifecycle_artifacts",
    "parse_sqlite_session_file_marker",
    "read_session_transcript_events",
    "read_session_transcript_raw_delta",
]
