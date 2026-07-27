"""jarvis.routing.agent_id — canonical agent-id normalization (non-raising core).

OpenClaw parity: mirrors ``packages/normalization-core/src/agent-id.ts``.

NOTE: distinct from the legacy plugin-SDK ``routing.routing.normalize_agent_id``
(which raises on reserved ids and is kept for jarvis_sdk compatibility).
This is the OpenClaw *core* contract: never raises, always returns a
filesystem-safe canonical id, falling back to ``"main"``.
"""

from __future__ import annotations

import re

DEFAULT_AGENT_ID = "main"
_VALID_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$", re.IGNORECASE)
_INVALID_CHARS_RE = re.compile(r"[^a-z0-9_-]+")
_LEADING_DASH_RE = re.compile(r"^-+")
_TRAILING_DASH_RE = re.compile(r"-+$")


def normalize_agent_id(value: object) -> str:
    """Normalize an agent id to its filesystem-safe canonical form.

    Mirrors ``normalizeAgentId``: trim; empty → ``"main"``; already-valid
    ids are lowered; otherwise invalid chars collapse to ``-``, edge
    dashes strip, truncate to 64 chars, empty result → ``"main"``.
    Never raises.
    """
    trimmed = (value if isinstance(value, str) else "").strip()
    if not trimmed:
        return DEFAULT_AGENT_ID
    normalized = trimmed.lower()
    if _VALID_ID_RE.match(trimmed):
        return normalized
    cleaned = _INVALID_CHARS_RE.sub("-", normalized)
    cleaned = _LEADING_DASH_RE.sub("", cleaned)
    cleaned = _TRAILING_DASH_RE.sub("", cleaned)
    return cleaned[:64] or DEFAULT_AGENT_ID


def is_valid_agent_id(value: object) -> bool:
    """Return whether ``value`` is already a canonical agent-id input."""
    trimmed = (value if isinstance(value, str) else "").strip()
    return bool(trimmed) and _VALID_ID_RE.match(trimmed) is not None


__all__ = ["DEFAULT_AGENT_ID", "is_valid_agent_id", "normalize_agent_id"]
