"""jarvis.agents.sessions.session_manager_id — session id helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/session-manager-id.ts``.

Two small helpers used by every session file:
- :func:`create_session_id` — the canonical
  per-session UUID (UUID v7, time-sortable).
- :func:`generate_session_entry_id` — short
  8-char id for individual entries (messages,
  compactions, etc.) with collision avoidance.

Parity
======
- ``create_session_id() -> str`` (``session-manager-id.ts:4-6``) —
  returns a ``uuidv7()``.
- ``generate_session_entry_id(existing) -> str``
  (``session-manager-id.ts:9-16``) — tries up to
  100 random 8-char UUID prefixes; on collision
  exhaustion, falls back to a full UUID.

Phase 6.2 — session codec.
"""
from __future__ import annotations

import uuid

from jarvis_agent.uuid7 import uuidv7


def create_session_id() -> str:
    """Return a fresh, time-sortable session id.

    Mirrors ``createSessionId``
    (``session-manager-id.ts:4-6``). The Python
    port delegates to :func:`jarvis_agent.uuid7.uuidv7`
    (the agent-core port), which returns a 36-char
    canonical UUID v7 string.
    """
    return uuidv7()


def generate_session_entry_id(
    existing: "set[str] | object",
) -> str:
    """Generate a short, collision-checked entry id.

    Mirrors ``generateSessionEntryId``
    (``session-manager-id.ts:9-16``).

    Parameters
    ----------
    existing : set[str] | object
        A container that supports ``id in existing``
        (the OpenClaw source's ``has`` method on
        a ``Set``). In practice this is a ``set``
        of already-used ids; the function generates
        a fresh 8-char prefix until it finds a
        collision-free id. Up to 100 attempts; on
        collision exhaustion, the function falls
        back to a full UUID v4.

    Returns
    -------
    str
        An 8-character lowercase hex prefix (or a
        full 36-char UUID v4 string if the prefix
        space is exhausted).
    """
    for _ in range(100):
        # ``uuid.uuid4().hex[:8]`` matches the
        # OpenClaw ``randomUUID().slice(0, 8)``
        # exactly (8 lowercase hex chars from a
        # random UUID v4).
        candidate = uuid.uuid4().hex[:8]
        if candidate not in existing:
            return candidate
    # Collision-exhaustion fallback — match the
    # OpenClaw source's ``return randomUUID()``.
    return str(uuid.uuid4())


__all__ = [
    "create_session_id",
    "generate_session_entry_id",
]
