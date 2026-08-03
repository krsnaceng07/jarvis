"""jarvis.utils.utf8_truncate — UTF-8 byte-safe truncation helpers.

OpenClaw parity: mirrors ``openclaw-main/src/utils/utf8-truncate.ts``.

Public surface:

- :func:`truncate_utf8_prefix`
- :func:`truncate_utf8_suffix`
"""
from __future__ import annotations


def _is_continuation_byte(byte: int) -> bool:
    return (byte & 0xC0) == 0x80


def truncate_utf8_prefix(value: str, max_bytes: int) -> str:
    """Keep the longest UTF-8 prefix of ``value`` that fits within ``max_bytes``.

    Mirrors :func:`truncateUtf8Prefix` (``utils/utf8-truncate.ts``).
    """
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    end = max_bytes
    while end > 0 and _is_continuation_byte(encoded[end]):
        end -= 1
    return encoded[:end].decode("utf-8", errors="ignore")


def truncate_utf8_suffix(value: str, max_bytes: int) -> str:
    """Keep the longest UTF-8 suffix of ``value`` that fits within ``max_bytes``.

    Mirrors :func:`truncateUtf8Suffix` (``utils/utf8-truncate.ts``).
    """
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    start = len(encoded) - max_bytes
    while start < len(encoded) and _is_continuation_byte(encoded[start]):
        start += 1
    return encoded[start:].decode("utf-8", errors="ignore")


__all__ = [
    "truncate_utf8_prefix",
    "truncate_utf8_suffix",
]
