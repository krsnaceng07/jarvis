"""jarvis.utils.string_readers — string option + alias helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/string-readers.ts``.

Public surface:

- :func:`is_string_option`
- :func:`read_string_alias`
- :func:`read_trimmed_string_alias`
- :func:`strip_channel_prefix`
"""
from __future__ import annotations

from typing import Any, FrozenSet, List, Optional, Set, Union


def is_string_option(value: Any, options: Union[List[str], FrozenSet[str], Set[str]]) -> bool:
    """Return whether ``value`` is one of the given string options.

    Mirrors :func:`isStringOption` (``utils/string-readers.ts``).
    """
    return isinstance(value, str) and value in options


def read_string_value(value: Any) -> Optional[str]:
    """Return ``value`` as a non-empty string, else ``None``."""
    if isinstance(value, str) and value:
        return value
    return None


def read_string_alias(
    record: Any, keys: List[str]
) -> Optional[str]:
    """Return the first non-empty string from ``record`` at any of ``keys``.

    Mirrors :func:`readStringAlias` (``utils/string-readers.ts``).
    """
    if not isinstance(record, dict):
        return None
    for key in keys:
        value = read_string_value(record.get(key))
        if value is not None:
            return value
    return None


def read_trimmed_string_alias(
    record: Any, keys: List[str]
) -> Optional[str]:
    """Return the first trimmed non-empty string from ``record`` at any of ``keys``.

    Mirrors :func:`readTrimmedStringAlias` (``utils/string-readers.ts``).
    """
    if not isinstance(record, dict):
        return None
    for key in keys:
        value = record.get(key)
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
    return None


def strip_channel_prefix(value: Optional[str], channel_id: str) -> Optional[str]:
    """Strip ``channel:`` / ``chat:`` / ``user:`` / ``<channel_id>:`` prefix from ``value``.

    Mirrors :func:`stripChannelPrefix` (``utils/string-readers.ts``).
    """
    if not value:
        return None
    generic_prefixes = ("channel:", "chat:", "user:")
    for prefix in generic_prefixes:
        if value.startswith(prefix):
            return value[len(prefix):]
    prefix = f"{channel_id}:"
    if value.startswith(prefix):
        return value[len(prefix):]
    return value


__all__ = [
    "is_string_option",
    "read_string_alias",
    "read_trimmed_string_alias",
    "strip_channel_prefix",
]
