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


__all__ = [
    "SessionTranscriptTargetParams",
    "SqliteSessionFileMarker",
    "TranscriptRawDeltaPage",
    "build_session_transcript_target",
    "cleanup_session_lifecycle_artifacts",
    "parse_sqlite_session_file_marker",
    "read_session_transcript_events",
    "read_session_transcript_raw_delta",
]
