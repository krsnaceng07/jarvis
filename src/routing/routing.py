"""jarvis_sdk.routing — agent-id + session-key parsing.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/routing``'s
``normalizeAgentId``, ``parseAgentSessionKey``, and
``parseThreadSessionSuffix``. Used by every memory-touching
extension to canonicalize agent ids read from config or
session keys, and to extract the agent / thread segments
from OpenClaw session-key shapes.

Architecture
============
OpenClaw agent ids are case-insensitive strings with a small
normalization contract: trim, lowercase, and reject a fixed
list of reserved / invalid values. The Python port follows the
same contract so the host's agent resolution layer is
case-stable across the SDK boundary.

Session keys follow the shape ``agent:<agentId>:<rest>``.
``parseAgentSessionKey`` splits them into ``{"agentId", "rest"}``;
``parseThreadSessionSuffix`` strips a trailing ``:thread:<id>``
segment so the parent and threaded sessions share a key.

Parity
======
- ``normalize_agent_id(raw)`` → ``str`` (canonical form).
  Raises ``ValueError`` on empty / reserved ids.
- ``parse_agent_session_key(session_key)`` → ``dict | None``
  with ``agentId`` and ``rest`` fields; ``None`` if the key
  doesn't start with ``agent:``.
- ``parse_thread_session_suffix(session_key)`` → ``dict``
  with ``baseSessionKey`` (the part before ``:thread:<id>``)
  and ``threadSessionKey`` (the stripped suffix, or ``None``).
- The reserved set mirrors OpenClaw's set (pathological inputs
  that should never reach the plugin layer).
"""

from __future__ import annotations

from typing import Any

_RESERVED = frozenset(
    {
        "",
        "default",
        ".",
        "..",
        "/",
        "\\",
    }
)


def normalize_agent_id(raw: object) -> str:
    """Canonicalize an agent id.

    Mirrors ``openclaw/plugin-sdk/routing``'s ``normalizeAgentId``.
    Returns the lower-cased, trimmed string. Raises ``ValueError``
    on empty / reserved inputs.
    """
    if raw is None:
        raise ValueError("agent id must not be None")
    if not isinstance(raw, str):
        raise ValueError(f"agent id must be a string, got {type(raw).__name__}")
    normalized = raw.strip().lower()
    if normalized in _RESERVED:
        raise ValueError(f"agent id {raw!r} is reserved / invalid")
    if any(ch in normalized for ch in ("\n", "\r", "\t", "\0")):
        raise ValueError(f"agent id {raw!r} contains whitespace / null characters")
    return normalized


def parse_agent_session_key(session_key: object) -> dict[str, str] | None:
    """Parse ``agent:<id>:<rest>`` session keys.

    Mirrors ``openclaw/plugin-sdk/routing``'s
    ``parseAgentSessionKey``. Returns a dict with
    ``{"agentId", "rest"}`` when the key starts with
    ``agent:``, or ``None`` otherwise. The ``rest`` is the
    raw remainder (no lowercasing).
    """
    if not isinstance(session_key, str):
        return None
    if not session_key.startswith("agent:"):
        return None
    tail = session_key[len("agent:") :]
    if not tail:
        return None
    if ":" not in tail:
        return {"agentId": tail, "rest": ""}
    agent_id, rest = tail.split(":", 1)
    return {"agentId": agent_id, "rest": rest}


def parse_thread_session_suffix(session_key: object) -> dict[str, Any]:
    """Strip a trailing ``:thread:<id>`` from a session key.

    Mirrors ``openclaw/plugin-sdk/routing``'s
    ``parseThreadSessionSuffix``. Returns a dict with
    ``baseSessionKey`` (the part before the suffix; the
    original key when no suffix is present) and
    ``threadSessionKey`` (the stripped suffix, or ``None``).
    """
    if not isinstance(session_key, str) or not session_key:
        return {"baseSessionKey": "", "threadSessionKey": None}
    parts = session_key.rsplit(":thread:", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return {"baseSessionKey": session_key, "threadSessionKey": None}
    return {"baseSessionKey": parts[0], "threadSessionKey": parts[1]}


__all__ = [
    "normalize_agent_id",
    "parse_agent_session_key",
    "parse_thread_session_suffix",
]
