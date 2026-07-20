"""jarvis_sdk.string_coerce — defensive string coercion helpers.

OpenClaw parity: mirrors
``@openclaw/normalization-core/string-coerce``'s
``asOptionalRecord`` and ``normalizeLowercaseStringOrEmpty``.

Used by ``memory-lancedb`` to safely coerce user-supplied
JSON / message content into the shape the plugin expects
without raising on bad inputs.

Architecture
============
The memory extension reads message envelopes from channels
that may be any JSON shape. OpenClaw's ``asOptionalRecord``
treats everything that isn't a plain object as ``None``; the
``normalizeLowercaseStringOrEmpty`` helper coerces strings to
lowercase, falling back to ``""`` on bad input. Python's
runtime is more forgiving (duck-typing) but the same defensive
contract applies to the boundary where the plugin SDK hands
data to extension code.

Parity
======
- ``as_optional_record(value)`` → ``dict | None`` (input is
  coerced through ``dict(value)``; on TypeError / ValueError
  returns None).
- ``normalize_lowercase_string_or_empty(value)`` → ``str``
  (lower-cased, with the input as-is if it isn't a string).
"""
from __future__ import annotations

from typing import Any


def as_optional_record(value: object) -> dict[str, Any] | None:
    """Coerce ``value`` to a ``dict`` or return ``None``.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``asOptionalRecord``. Used to safely check ``msg.role``,
    ``msg.content``, etc., on a user-supplied message that may
    be any JSON shape.
    """
    if isinstance(value, dict):
        return value
    if value is None:
        return None
    try:
        return dict(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def normalize_lowercase_string_or_empty(value: object) -> str:
    """Lowercase ``value`` if it's a string; otherwise return ``""``.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``normalizeLowercaseStringOrEmpty``. Used for the
    ``category`` and ``channel`` fields in the memory-store
    call so the store can index by a stable lowercase key.
    """
    if isinstance(value, str):
        return value.strip().lower()
    return ""


__all__ = [
    "as_optional_record",
    "normalize_lowercase_string_or_empty",
]
