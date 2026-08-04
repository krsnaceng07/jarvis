"""jarvis.config.byte_size — byte-size config value parser.

OpenClaw parity: mirrors ``openclaw-main/src/config/byte-size.ts``.
"""
from __future__ import annotations

import re
from typing import Optional


_BYTE_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]*)\s*$")
_BYTE_UNITS = {
    "": 1,
    "b": 1,
    "kb": 1024,
    "k": 1024,
    "kib": 1024,
    "mb": 1024 * 1024,
    "m": 1024 * 1024,
    "mib": 1024 * 1024,
    "gb": 1024 * 1024 * 1024,
    "g": 1024 * 1024 * 1024,
    "gib": 1024 * 1024 * 1024,
    "tb": 1024 * 1024 * 1024 * 1024,
    "t": 1024 * 1024 * 1024 * 1024,
    "tib": 1024 * 1024 * 1024 * 1024,
}


def parse_byte_size(value: str, *, default_unit: str = "b") -> int:
    """Parse a byte-size string like ``"2mb"`` or ``"1024"`` into bytes.

    Focused minimal port of OpenClaw's :func:`parseByteSize`.
    """
    if not isinstance(value, str):
        raise ValueError(f"byte size must be a string, got {type(value).__name__}")
    m = _BYTE_SIZE_RE.match(value)
    if not m:
        raise ValueError(f"invalid byte size: {value!r}")
    n = float(m.group(1))
    unit = (m.group(2) or default_unit).lower()
    if unit not in _BYTE_UNITS:
        raise ValueError(f"unknown byte size unit: {unit!r}")
    return int(n * _BYTE_UNITS[unit])


def parse_non_negative_byte_size(value) -> Optional[int]:
    """Parse an optional byte-size value from config.

    Mirrors :func:`parseNonNegativeByteSize`
    (``shared/config/byte-size.ts``).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        i = int(value)
        return i if i >= 0 else None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        try:
            bytes_ = parse_byte_size(trimmed, default_unit="b")
            return bytes_ if bytes_ >= 0 else None
        except ValueError:
            return None
    return None


def is_valid_non_negative_byte_size_string(value: str) -> bool:
    """Validate a byte-size string accepted by config.

    Mirrors :func:`isValidNonNegativeByteSizeString`
    (``shared/config/byte-size.ts``).
    """
    return parse_non_negative_byte_size(value) is not None


__all__ = [
    "parse_byte_size",
    "parse_non_negative_byte_size",
    "is_valid_non_negative_byte_size_string",
]
