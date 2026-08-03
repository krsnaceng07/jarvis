"""jarvis.utils.boolean — boolean coercion helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/boolean.ts``.

Public surface:

- :func:`as_boolean`
- :func:`parse_boolean_value`
- :data:`DEFAULT_TRUTHY`
- :data:`DEFAULT_FALSY`
"""
from __future__ import annotations

from typing import Any, List, Optional, Set


DEFAULT_TRUTHY: List[str] = ["true", "1", "yes", "on"]
DEFAULT_FALSY: List[str] = ["false", "0", "no", "off"]
DEFAULT_TRUTHY_SET: Set[str] = set(DEFAULT_TRUTHY)
DEFAULT_FALSY_SET: Set[str] = set(DEFAULT_FALSY)


def as_boolean(value: Any) -> Optional[bool]:
    """Return only real boolean values; leave boolean-like strings for explicit parsing.

    Mirrors :func:`asBoolean` (``utils/boolean.ts``).
    """
    if isinstance(value, bool):
        return value
    return None


def parse_boolean_value(
    value: Any,
    options: Optional[dict] = None,
) -> Optional[bool]:
    """Parse booleans and configured string literals; return None for ambiguous input.

    Mirrors :func:`parseBooleanValue` (``utils/boolean.ts``).
    """
    options = options or {}
    boolean_value = as_boolean(value)
    if boolean_value is not None:
        return boolean_value
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    truthy = options.get("truthy", DEFAULT_TRUTHY) if options else DEFAULT_TRUTHY
    falsy = options.get("falsy", DEFAULT_FALSY) if options else DEFAULT_FALSY
    truthy_set = DEFAULT_TRUTHY_SET if truthy is DEFAULT_TRUTHY else set(truthy)
    falsy_set = DEFAULT_FALSY_SET if falsy is DEFAULT_FALSY else set(falsy)
    if normalized in truthy_set:
        return True
    if normalized in falsy_set:
        return False
    return None


__all__ = [
    "DEFAULT_TRUTHY",
    "DEFAULT_FALSY",
    "as_boolean",
    "parse_boolean_value",
]
