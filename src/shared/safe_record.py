"""jarvis.shared.safe_record — defensive object/array access helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/safe-record.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def is_record_without_throwing(value: Any) -> bool:
    """Return whether ``value`` is a plain object, guarding against traps.

    Mirrors :func:`isRecordWithoutThrowing` (``shared/safe-record.ts``).
    """
    try:
        # In JS, `Boolean({}) === true` (objects are truthy even when empty);
        # in Python `bool({})` is False, so we cannot rely on truthiness.
        return value is not None and isinstance(value, dict) and not isinstance(value, list)
    except Exception:  # noqa: BLE001
        return False


def read_record_value(value: Any, key: str) -> Any:
    """Read one property from a record-like value without letting traps escape.

    Mirrors :func:`readRecordValue` (``shared/safe-record.ts``).
    """
    if not is_record_without_throwing(value):
        return None
    try:
        return value[key]
    except Exception:  # noqa: BLE001
        return None


def copy_array_entries(value: Any) -> List[Any]:
    """Copy array entries defensively from a value that may throw on access.

    Mirrors :func:`copyArrayEntries` (``shared/safe-record.ts``).
    """
    try:
        is_array = isinstance(value, list)
    except Exception:  # noqa: BLE001
        return []
    if not is_array:
        return []
    try:
        length = len(value)
    except Exception:  # noqa: BLE001
        return []
    out: List[Any] = []
    for i in range(length):
        try:
            out.append(value[i])
        except Exception:  # noqa: BLE001
            continue
    return out


def copy_record_entries(value: Any) -> List[Tuple[str, Any]]:
    """Copy record entries whose values are also record-shaped.

    Mirrors :func:`copyRecordEntries` (``shared/safe-record.ts``).
    """
    if not is_record_without_throwing(value):
        return []
    try:
        keys = list(value.keys())
    except Exception:  # noqa: BLE001
        return []
    out: List[Tuple[str, Any]] = []
    for k in keys:
        entry = read_record_value(value, k)
        if is_record_without_throwing(entry):
            out.append((k, entry))
    return out


__all__ = [
    "is_record_without_throwing",
    "read_record_value",
    "copy_array_entries",
    "copy_record_entries",
]
