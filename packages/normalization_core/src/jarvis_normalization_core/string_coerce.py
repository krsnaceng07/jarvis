"""jarvis_sdk.string_coerce — defensive string coercion helpers.

OpenClaw parity: mirrors
``@openclaw/normalization-core/string-coerce``'s
``asOptionalRecord``, ``normalizeLowercaseStringOrEmpty``,
``normalizeStringEntries``, ``normalizeOptionalString``, and
``uniqueStrings``.

Used by ``memory-lancedb`` to safely coerce user-supplied
JSON / message content into the shape the plugin expects
without raising on bad inputs; used by ``active-memory`` to
normalize config arrays and probe tool result text.

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
- ``normalize_string_entries(value)`` → ``list[str]``
  (deduplicated, lower-cased; non-string / empty entries
  dropped).
- ``normalize_optional_string(value)`` → ``str | None``
  (trimmed string or ``None`` for empty / non-string).
- ``unique_strings(values)`` → ``list[str]`` (deduplicated,
  preserves order; non-string entries dropped).
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


def normalize_string_entries(value: object) -> list[str]:
    """Normalize a list of strings, deduplicated, lower-cased.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``normalizeStringEntries``. Non-string entries are
    dropped; empty / whitespace-only entries are dropped.
    """
    if not isinstance(value, list | tuple):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        normalized = entry.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def normalize_optional_lowercase_string(value: object) -> str | None:
    """Return a trimmed, lowercased string, or ``None`` for empty / non-string.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``normalizeOptionalLowercaseString``. Used by routing helpers
    that want channel/agent ids in canonical lowercase form.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip().lower()
    return trimmed if trimmed else None


def normalize_optional_string(value: object) -> str | None:
    """Return a trimmed string, or ``None`` for empty / non-string.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``normalizeOptionalString``.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def normalize_trimmed_string_list(value: object) -> list[str]:
    """Normalize an array-backed string list, dropping empty / non-string entries.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``normalizeTrimmedStringList``. Returns ``[]`` for non-array
    input; each surviving entry is the trimmed string.
    """
    if not isinstance(value, list | tuple):
        return []
    out: list[str] = []
    for entry in value:
        normalized = normalize_optional_string(entry)
        if normalized is not None:
            out.append(normalized)
    return out


def normalize_single_or_trimmed_string_list(value: object) -> list[str]:
    """Normalize a string-or-list input into a string list.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``normalizeSingleOrTrimmedStringList``. A bare string is
    wrapped into a single-element list; an array is normalized
    via :func:`normalize_trimmed_string_list`; anything else
    (including ``None``) returns ``[]``.
    """
    if isinstance(value, list | tuple):
        return normalize_trimmed_string_list(value)
    normalized = normalize_optional_string(value)
    return [normalized] if normalized is not None else []


def unique_strings(values: object) -> list[str]:
    """Deduplicate a list of strings, preserving order.

    Mirrors ``@openclaw/normalization-core/string-coerce``'s
    ``uniqueStrings``. Non-string entries are dropped. Used
    by ``active-memory`` to build a stable debug-line summary
    without repeats.
    """
    if not isinstance(values, list | tuple):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for entry in values:
        if not isinstance(entry, str):
            continue
        if entry in seen:
            continue
        seen.add(entry)
        out.append(entry)
    return out


def lowercase_preserving_whitespace(value: object) -> str:
    """Lowercase ``value`` while preserving internal whitespace.

    Mirrors ``openclaw/plugin-sdk/string-coerce-runtime``'s
    ``lowercasePreservingWhitespace``. Coerces non-string
    inputs via ``str(value)``. Used by ``memory-wiki`` to
    canonicalize Windows paths for the artifact-key resolver
    (case-insensitive but whitespace-sensitive). Trims
    leading/trailing whitespace, then lowercases, but
    preserves runs of internal whitespace.
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    return text.strip().lower()


__all__ = [
    "as_optional_record",
    "lowercase_preserving_whitespace",
    "normalize_lowercase_string_or_empty",
    "normalize_optional_string",
    "normalize_single_or_trimmed_string_list",
    "normalize_string_entries",
    "normalize_trimmed_string_list",
    "unique_strings",
]
