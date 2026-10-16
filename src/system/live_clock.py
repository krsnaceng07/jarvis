"""jarvis.system.live_clock — Live system clock and temporal context provider.

Mirrors OpenClaw's date-time.ts (buildTemporalContextSection, formatUserTime).
Provides ground-truth live system clock, exact timezone resolution, date formatting,
and temporal context generation so JARVIS never hallucinates or guesses time.
"""

from __future__ import annotations

import datetime
import time
import zoneinfo
from typing import Any, Dict, Optional


def _get_ordinal_suffix(day: int) -> str:
    """Return ordinal suffix for day of month (e.g. 1st, 2nd, 3rd, 4th)."""
    if 11 <= day <= 13:
        return "th"
    remainder = day % 10
    if remainder == 1:
        return "st"
    elif remainder == 2:
        return "nd"
    elif remainder == 3:
        return "rd"
    return "th"


class LiveClock:
    """Live system clock querying the operating system with microsecond precision."""

    @staticmethod
    def get_timezone() -> str:
        """Resolve current local timezone name (IANA or local identifier)."""
        try:
            local_tz = datetime.datetime.now().astimezone().tzinfo
            if local_tz:
                tz_name = str(local_tz)
                if tz_name:
                    return tz_name
        except Exception:
            pass
        return time.tzname[0] if time.tzname else "UTC"

    @classmethod
    def get_now(cls, tz_name: Optional[str] = None) -> datetime.datetime:
        """Return current datetime localized to the system or requested timezone."""
        if tz_name:
            try:
                tz = zoneinfo.ZoneInfo(tz_name)
                return datetime.datetime.now(tz)
            except Exception:
                pass
        return datetime.datetime.now().astimezone()

    @classmethod
    def get_current_datetime(cls, tz_name: Optional[str] = None) -> Dict[str, Any]:
        """Return structured dictionary of the exact current date, time, and timezone."""
        now = cls.get_now(tz_name)
        day = now.day
        suffix = _get_ordinal_suffix(day)

        time_12h = now.strftime("%I:%M:%S %p").lstrip("0")
        time_24h = now.strftime("%H:%M:%S")
        weekday = now.strftime("%A")
        month_name = now.strftime("%B")
        year = now.year
        date_str = now.strftime("%Y-%m-%d")
        tz_str = str(now.tzinfo) if now.tzinfo else "UTC"
        utc_offset = now.strftime("%z")
        formatted_human = f"{weekday}, {month_name} {day}{suffix}, {year} - {time_12h}"

        return {
            "datetime_iso": now.isoformat(),
            "date": date_str,
            "time_12h": time_12h,
            "time_24h": time_24h,
            "weekday": weekday,
            "day": day,
            "month": now.month,
            "month_name": month_name,
            "year": year,
            "timezone": tz_str,
            "utc_offset": utc_offset,
            "timestamp": now.timestamp(),
            "formatted_human": formatted_human,
            "source": "host_system_clock",
            "verified": True,
        }

    @classmethod
    def get_current_date(cls) -> str:
        """Return ISO formatted date string (YYYY-MM-DD)."""
        return cls.get_now().strftime("%Y-%m-%d")

    @classmethod
    def get_current_time(cls, use_24h: bool = False) -> str:
        """Return formatted current time string."""
        now = cls.get_now()
        if use_24h:
            return now.strftime("%H:%M:%S")
        return now.strftime("%I:%M:%S %p").lstrip("0")

    @classmethod
    def get_day_of_week(cls) -> str:
        """Return day of the week (e.g. Saturday)."""
        return cls.get_now().strftime("%A")

    @classmethod
    def build_temporal_context_prompt(cls, tz_name: Optional[str] = None) -> str:
        """Render OpenClaw-grade Temporal Context section for system instruction."""
        info = cls.get_current_datetime(tz_name)
        lines = [
            "## Temporal Context",
            f"Current date: {info['date']} ({info['weekday']})",
            f"Current time: {info['time_12h']} (24h: {info['time_24h']})",
            f"Time zone: {info['timezone']} (UTC {info['utc_offset']})",
            f"Exact stamp: {info['formatted_human']}",
            "Rule: Always answer date/time queries using this live host context or system_info tool.",
        ]
        return "\n".join(lines)
