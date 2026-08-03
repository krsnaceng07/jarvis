"""jarvis.shared.lobster_day — shared lobster-day calendar hash.

OpenClaw parity: mirrors ``openclaw-main/src/shared/lobster-day.ts``.

The CLI banner and Control UI pet-coordinate agree on this one function so
both surfaces always agree on the date. Roughly one day in sixteen hits.
"""
from __future__ import annotations

from datetime import datetime


def lobster_day_hash(now: datetime) -> int:
    """FNV-1a hash of the calendar date.

    Mirrors :func:`lobsterDayHash` (``shared/lobster-day.ts``).
    """
    key = f"{now.year}-{now.month}-{now.day}"
    hash_ = 0x811C9DC5
    for ch in key:
        hash_ ^= ord(ch)
        hash_ = (hash_ * 0x01000193) & 0xFFFFFFFF
    return hash_


def is_lobster_day(now: datetime) -> bool:
    """Return True if ``now`` lands on the FNV-mod-16 == 3 day.

    Mirrors :func:`isLobsterDay` (``shared/lobster-day.ts``).
    """
    return lobster_day_hash(now) % 16 == 3


__all__ = ["lobster_day_hash", "is_lobster_day"]
