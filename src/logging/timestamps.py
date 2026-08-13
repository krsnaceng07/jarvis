"""jarvis.logging.timestamps — log timestamp formatting helpers.

OpenClaw parity: mirrors ``openclaw-main/src/logging/timestamps.ts``.

Public surface:

- :func:`format_timestamp`
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional


_VALID_TZ_CACHE: dict = {}
_FMT_CACHE: dict = {}


def _is_valid_time_zone(tz: str) -> bool:
    cached = _VALID_TZ_CACHE.get(tz)
    if cached is not None:
        return cached
    valid = False
    try:
        # Python 3.9+: zoneinfo; but also accept plain UTC alias
        from zoneinfo import ZoneInfo

        ZoneInfo(tz)
        valid = True
    except Exception:
        valid = tz.upper() in ("UTC", "GMT")
    _VALID_TZ_CACHE[tz] = valid
    return valid


def _resolve_effective_time_zone(time_zone: Optional[str]) -> str:
    explicit = time_zone or os.environ.get("TZ")
    if explicit and _is_valid_time_zone(explicit):
        return explicit
    # Fallback to host local time zone.
    return datetime.now().astimezone().tzinfo.tzname(None) or "UTC"


def _format_offset(td: Any) -> str:
    total_seconds = int(td.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    abs_seconds = abs(total_seconds)
    hours = abs_seconds // 3600
    minutes = (abs_seconds % 3600) // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _resolve_tzinfo(tz: str) -> Any:
    if tz.upper() in {"UTC", "GMT"}:
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(tz)
    except Exception:
        return timezone.utc


def _format_iso_like(date: datetime, tz: str) -> str:
    """Render a date as ``YYYY-MM-DDTHH:MM:SS.mmm+HH:MM`` in ``tz``."""
    target = date.astimezone(_resolve_tzinfo(tz))
    offset = _format_offset(target.utcoffset())
    return (
        f"{target.year:04d}-{target.month:02d}-{target.day:02d}"
        f"T{target.hour:02d}:{target.minute:02d}:{target.second:02d}"
        f".{target.microsecond // 1000:03d}{offset}"
    )


def format_timestamp(date: Optional[datetime] = None, options: Optional[dict] = None) -> str:
    """Format ``date`` for log lines at short/medium/long granularity.

    Mirrors :func:`formatTimestamp` (``logging/timestamps.ts``).
    """
    options = options or {}
    style = options.get("style", "medium")
    if style not in ("short", "medium", "long"):
        raise ValueError("Unsupported timestamp style")
    time_zone = options.get("timeZone")
    effective_tz = _resolve_effective_time_zone(time_zone)
    target = date or datetime.now(timezone.utc)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    try:
        localized = target.astimezone(_resolve_tzinfo(effective_tz))
    except Exception:
        localized = target.astimezone(timezone.utc)
    offset = _format_offset(localized.utcoffset())
    if style == "short":
        return f"{localized.hour:02d}:{localized.minute:02d}:{localized.second:02d}{offset}"
    if style == "medium":
        ms = localized.microsecond // 1000
        return f"{localized.hour:02d}:{localized.minute:02d}:{localized.second:02d}.{ms:03d}{offset}"
    return _format_iso_like(target, effective_tz)


__all__ = ["format_timestamp"]
