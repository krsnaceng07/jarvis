"""Cron expression parser and schedule evaluation."""

from __future__ import annotations

import re
from datetime import datetime

# ISO timestamp pattern (one-shot jobs).
ISO_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_ISO_TS_RE = ISO_TS_RE


def is_iso_timestamp(schedule: str) -> bool:
    """Return True if ``schedule`` looks like an ISO-8601 timestamp."""
    return bool(_ISO_TS_RE.match(schedule.strip()))


def cron_matches(expr: str, when: datetime) -> bool:
    """Return True if ``when`` matches the 5-field cron expression.

    Fields: minute hour day-of-month month day-of-week.
    """
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            f"cron expression must have 5 fields (minute hour dom mon dow); "
            f"got {len(fields)}: {expr!r}"
        )
    minute, hour, dom, mon, dow = fields
    return (
        field_matches(minute, when.minute, 0, 59)
        and field_matches(hour, when.hour, 0, 23)
        and field_matches(dom, when.day, 1, 31)
        and field_matches(mon, when.month, 1, 12)
        and field_matches(dow, when.weekday(), 0, 6)  # Mon=0, Sun=6
    )


_cron_matches = cron_matches


def field_matches(spec: str, value: int, lo: int, hi: int) -> bool:
    """Return True if a single cron field matches ``value``."""
    for part in spec.split(","):
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = max(1, int(step_str))
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            s, e = base.split("-", 1)
            start, end = int(s), int(e)
        else:
            start = end = int(base)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


_field_matches = field_matches


__all__ = [
    "ISO_TS_RE",
    "_ISO_TS_RE",
    "_cron_matches",
    "_field_matches",
    "cron_matches",
    "field_matches",
    "is_iso_timestamp",
]
