"""jarvis.shared.iso_time — ISO-like date validation.

OpenClaw parity: mirrors ``openclaw-main/src/shared/iso-time.ts``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

#: ISO-like absolute date+optional-time regex used by existing callers.
_ISO_ABSOLUTE_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[Tt](\d{2}):(\d{2})(?::(\d{2})(\.\d+)?)?(?:[Zz]|[+-]\d{2}:?\d{2})?)?$"
)


def has_valid_iso_calendar_components(raw: str) -> bool:
    """Check the calendar components of the ISO-like forms accepted by callers.

    Mirrors :func:`hasValidIsoCalendarComponents` (``shared/iso-time.ts``).
    """
    if not isinstance(raw, str):
        return False
    match = _ISO_ABSOLUTE_RE.match(raw)
    if not match:
        return False
    year_s, month_s, day_s = match.group(1), match.group(2), match.group(3)
    hour_s = match.group(4) or "0"
    minute_s = match.group(5) or "0"
    second_s = match.group(6) or "0"
    fraction_s = match.group(7)
    try:
        year = int(year_s)
        month = int(month_s)
        day = int(day_s)
        hour = int(hour_s)
        minute = int(minute_s)
        second = int(second_s)
    except ValueError:
        return False
    if fraction_s:
        ms_text = fraction_s[1:4].ljust(3, "0")
        try:
            millisecond = int(ms_text)
        except ValueError:
            millisecond = 0
    else:
        millisecond = 0
    has_zero_fraction = not fraction_s or not re.search(r"[1-9]", fraction_s)
    is_end_of_day = hour == 24 and minute == 0 and second == 0 and has_zero_fraction

    # Date.parse rolls invalid calendar components forward, so validate independently.
    try:
        probe = datetime(
            year,
            month,
            day,
            0 if is_end_of_day else hour,
            minute,
            second,
            millisecond * 1000,
            tzinfo=timezone.utc,
        )
    except ValueError:
        return False
    return (
        probe.year == year
        and probe.month == month
        and probe.day == day
        and probe.hour == (0 if is_end_of_day else hour)
        and probe.minute == minute
        and probe.second == second
        and probe.microsecond // 1000 == millisecond
    )


__all__ = ["has_valid_iso_calendar_components"]
