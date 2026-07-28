"""jarvis.sessions.session_store — SessionStore protocol + in-memory impl.

OpenClaw parity: mirrors the shape of the OpenClaw session
store (the TS side uses a SQLite-backed store; the Python
port ships an in-memory implementation in this slice).

The store is the per-agent, per-session-key record
authoritative. It owns:
- The session metadata (kind, owner agent, created/updated).
- A list of (id, kind, payload) transcript entries.
- Optional ``parent_session_key`` and ``thread_id`` for
  channel/thread sub-sessions.

The store is single-process; the Phase 5.14b SQLite-backed
port is gated on user schema approval (AGENTS.md §"SQLite
schema gate") and will reuse the same protocol.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One session's metadata + transcript entries.

    The Python port is structurally identical to the OpenClaw
    session-state event kinds: every entry is a
    ``(id, kind, payload)`` triple; the metadata captures
    agent / kind / created / updated at.
    """

    session_key: str
    agent_id: str
    kind: str  # "direct" | "channel" | "thread" | "cron" | "unknown"
    created_at: str
    updated_at: str
    parent_session_key: str | None = None
    thread_id: str | None = None
    entries: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def with_entry(self, entry: dict[str, Any]) -> "SessionRecord":
        """Return a new ``SessionRecord`` with ``entry`` appended.

        Mirrors the immutable-update pattern used in the
        OpenClaw store: every write produces a new record;
        readers see the snapshot they grabbed.
        """
        now = _now_iso()
        return SessionRecord(
            session_key=self.session_key,
            agent_id=self.agent_id,
            kind=self.kind,
            created_at=self.created_at,
            updated_at=now,
            parent_session_key=self.parent_session_key,
            thread_id=self.thread_id,
            entries=(*self.entries, entry),
        )


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _new_session_id() -> str:
    """Return a fresh UUID-shaped session id."""
    return str(uuid.uuid4())


class SessionStore(Protocol):
    """The protocol the agent_runtime and runner code use.

    Implementations are responsible for atomicity (the
    Python in-memory variant uses a ``threading.Lock`` per
    session; the SQLite-backed variant will use a
    transaction).
    """

    def get_or_create(
        self,
        *,
        session_key: str,
        agent_id: str,
        kind: str,
        parent_session_key: str | None = None,
        thread_id: str | None = None,
    ) -> SessionRecord: ...

    def append_entry(
        self, session_key: str, entry: dict[str, Any]
    ) -> SessionRecord: ...

    def get(self, session_key: str) -> SessionRecord | None: ...

    def list_sessions(self, agent_id: str | None = None) -> list[SessionRecord]:
        """Return every session, optionally filtered by ``agent_id``."""
        ...


class InMemorySessionStore:
    """Thread-safe in-memory implementation of the ``SessionStore`` protocol.

    Single-process; sessions live for the process lifetime. The
    ``reset`` helper is the test surface for clearing the
    store between tests.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Drop every session. Test-only helper."""
        with self._lock:
            self._sessions.clear()

    def get(self, session_key: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_key)

    def get_or_create(
        self,
        *,
        session_key: str,
        agent_id: str,
        kind: str,
        parent_session_key: str | None = None,
        thread_id: str | None = None,
    ) -> SessionRecord:
        with self._lock:
            existing = self._sessions.get(session_key)
            if existing is not None:
                return existing
            now = _now_iso()
            record = SessionRecord(
                session_key=session_key,
                agent_id=agent_id,
                kind=kind,
                created_at=now,
                updated_at=now,
                parent_session_key=parent_session_key,
                thread_id=thread_id,
            )
            self._sessions[session_key] = record
            return record

    def append_entry(
        self, session_key: str, entry: dict[str, Any]
    ) -> SessionRecord:
        with self._lock:
            current = self._sessions.get(session_key)
            if current is None:
                raise KeyError(
                    f"session_key {session_key!r} not found; call get_or_create first"
                )
            updated = current.with_entry(entry)
            self._sessions[session_key] = updated
            return updated

    def list_sessions(self, agent_id: str | None = None) -> list[SessionRecord]:
        with self._lock:
            sessions = list(self._sessions.values())
        if agent_id is not None:
            sessions = [s for s in sessions if s.agent_id == agent_id]
        return sessions


# Module-level singleton for the host runtime; tests construct
# their own per-test stores via ``InMemorySessionStore()``.
_default_store: InMemorySessionStore | None = None
_default_store_lock = threading.Lock()


def get_default_session_store() -> InMemorySessionStore:
    """Return the process-wide default ``InMemorySessionStore``.

    Lazy-initialized on first call so importing this module
    doesn't open any state. Tests should construct their own
    ``InMemorySessionStore()`` to avoid sharing state.
    """
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = InMemorySessionStore()
        return _default_store


def reset_default_session_store() -> None:
    """Reset the process-wide default store. Test-only helper."""
    global _default_store
    with _default_store_lock:
        if _default_store is not None:
            _default_store.reset()


__all__ = [
    "InMemorySessionStore",
    "SessionRecord",
    "SessionStore",
    "get_default_session_store",
    "reset_default_session_store",
]
