"""jarvis_session_core.session_id — canonical session-id shape + helpers.

OpenClaw parity: mirrors ``src/sessions/session-id.ts``.

A canonical session id is UUID-shaped (8-4-4-4-12 hex). The
helper answers whether a raw text could be one; it does not
validate that the id is currently in use, just the shape.
"""

from __future__ import annotations

import re

_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def looks_like_session_id(value: object) -> bool:
    """Return True if ``value`` is a UUID-shaped session id.

    Mirrors OpenClaw's ``looksLikeSessionId``: trim then regex
    match. Non-string inputs return False.
    """
    if not isinstance(value, str):
        return False
    return bool(_SESSION_ID_RE.match(value.strip()))


__all__ = ["looks_like_session_id"]
