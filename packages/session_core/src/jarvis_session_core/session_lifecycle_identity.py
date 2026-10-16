"""Session lifecycle identity normalization.

Mirrors OpenClaw's ``extensions/sessions/session-lifecycle-identity.ts``:
``normalize_session_identities`` (sorts a deduped, trimmed
list of identities as ``json([scope, identity])``) +
``decode_session_identity`` (the inverse). Used to identify
per-agent session lifecycle hooks.
"""

from __future__ import annotations

import json
from typing import Iterable


def normalize_session_identities(scope: str, identities: Iterable[str | None]) -> list[str]:
    """Normalize a list of identities into sorted, deduped JSON tuples.

    Each identity is trimmed; falsy values are dropped. The
    result is a list of ``json.dumps([scope, identity])``
    strings, sorted in natural order. Mirrors the TS
    ``normalizeSessionIdentities``.
    """
    normalized_scope = scope.strip()
    if not normalized_scope:
        raise ValueError("session lifecycle scope is required")
    seen: set[str] = set()
    out: list[str] = []
    for identity in identities:
        if identity is None:
            continue
        trimmed = identity.strip()
        if not trimmed:
            continue
        if trimmed in seen:
            continue
        seen.add(trimmed)
        out.append(json.dumps([normalized_scope, trimmed], separators=(",", ":")))
    out.sort()
    return out


def decode_session_identity(
    normalized_identity: str,
) -> dict[str, str] | None:
    """Decode a normalized session identity back to ``{scope, identity}``.

    Returns ``None`` for non-strings, malformed JSON, or
    shapes that don't match the ``[scope, identity]``
    two-element string tuple. Mirrors the TS
    ``decodeSessionIdentity``.
    """
    if not isinstance(normalized_identity, str):
        return None
    try:
        decoded = json.loads(normalized_identity)
    except (json.JSONDecodeError, ValueError):
        return None
    if (
        not isinstance(decoded, list)
        or len(decoded) != 2
        or not isinstance(decoded[0], str)
        or not isinstance(decoded[1], str)
    ):
        return None
    return {"scope": decoded[0], "identity": decoded[1]}


__all__ = [
    "decode_session_identity",
    "normalize_session_identities",
]
