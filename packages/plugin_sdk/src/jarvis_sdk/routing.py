"""jarvis_sdk.routing — agent-id normalization.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/routing``'s
``normalizeAgentId``. Used by every memory-touching extension
to canonicalize agent ids read from config or session keys.

Architecture
============
OpenClaw agent ids are case-insensitive strings with a small
normalization contract: trim, lowercase, and reject a fixed
list of reserved / invalid values. The Python port follows the
same contract so the host's agent resolution layer is
case-stable across the SDK boundary.

Parity
======
- ``normalize_agent_id(raw)`` → ``str`` (canonical form).
  Raises ``ValueError`` on empty / reserved ids.
- The reserved set mirrors OpenClaw's set (pathological inputs
  that should never reach the plugin layer).
"""

from __future__ import annotations

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


__all__ = ["normalize_agent_id"]
