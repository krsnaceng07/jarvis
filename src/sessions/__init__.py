"""jarvis.sessions — Session transcript runtime + minimal session store.

OpenClaw parity: mirrors a focused subset of
``src/sessions/``:

- ``src/sessions/session-id.ts`` (UUID shape) →
  ``session_id.py``
- ``src/sessions/classify-session-kind.ts`` (kind
  classifier) → ``classify_session_kind.py``
- The Python in-memory ``SessionStore`` (``session_store.py``)
  is the minimal session-state surface that the
  ``agent_runtime`` + ``runner`` (Phase 5.15) need; the
  full SQLite-backed port is gated on user schema approval
  (AGENTS.md §"SQLite schema gate") and lands in Phase 5.14b.

The 36 remaining OpenClaw session files
(``session-state-events``, ``session-lifecycle-admission``,
``session-upstream-monitor``, ``user-turn-transcript``, ...)
will land incrementally; the current slice is the
minimum the agent_runtime needs to actually run.

This package re-exports the public surface:

- ``SessionTranscriptTargetParams``,
  ``SqliteSessionFileMarker``,
  ``TranscriptRawDeltaPage``,
  ``build_session_transcript_target``,
  ``cleanup_session_lifecycle_artifacts``,
  ``parse_sqlite_session_file_marker``,
  ``read_session_transcript_events``,
  ``read_session_transcript_raw_delta``
  from ``session_transcript_runtime``;
- ``looks_like_session_id`` from ``session_id``;
- ``classify_session_kind``, ``is_valid_session_kind``
  from ``classify_session_kind``;
- ``InMemorySessionStore``, ``SessionRecord``,
  ``SessionStore``, ``get_default_session_store``,
  ``reset_default_session_store`` from ``session_store``.
"""
from __future__ import annotations

from .classify_session_kind import (
    classify_session_kind,
    is_valid_session_kind,
)
from .session_id import looks_like_session_id
from .session_store import (
    InMemorySessionStore,
    SessionRecord,
    SessionStore,
    get_default_session_store,
    reset_default_session_store,
)
from .session_transcript_runtime import (  # noqa: F401
    SessionTranscriptTargetParams,
    SqliteSessionFileMarker,
    TranscriptRawDeltaPage,
    build_session_transcript_target,
    cleanup_session_lifecycle_artifacts,
    parse_sqlite_session_file_marker,
    read_session_transcript_events,
    read_session_transcript_raw_delta,
)
