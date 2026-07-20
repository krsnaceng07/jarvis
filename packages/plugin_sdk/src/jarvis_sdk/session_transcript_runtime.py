"""jarvis_sdk.session_transcript_runtime — session transcript target params.

OpenClaw parity: mirrors
``openclaw/plugin-sdk/session-transcript-runtime``'s
``SessionTranscriptTargetParams``.

Used by ``active-memory`` to pass the target session id /
agent id / scope into the host's transcript-reading
helpers. The OpenClaw shape is a frozen dict; the Python
port uses a frozen dataclass so plugins can pass it as
a typed object.

Parity
======
- ``SessionTranscriptTargetParams`` fields:
  - ``session_id`` (required, str)
  - ``agent_id`` (optional, str)
  - ``session_key`` (optional, str)
  - ``scope`` (optional, str; one of
    ``"same-agent-private"`` | ``"shared"``)
- ``build_session_transcript_target(params)`` →
  ``SessionTranscriptTargetParams``: normalizes the input
  (drops empty strings, validates session_id is present).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionTranscriptTargetParams:
    """Identifies a session to read transcripts for.

    Mirrors OpenClaw's ``SessionTranscriptTargetParams``.
    """

    session_id: str
    agent_id: str | None = None
    session_key: str | None = None
    scope: str | None = None


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
    return SessionTranscriptTargetParams(
        session_id=session_id.strip(),
        agent_id=agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else None,
        session_key=session_key.strip()
        if isinstance(session_key, str) and session_key.strip()
        else None,
        scope=scope.strip() if isinstance(scope, str) and scope.strip() else None,
    )


__all__ = [
    "SessionTranscriptTargetParams",
    "build_session_transcript_target",
]
