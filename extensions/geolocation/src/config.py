"""Geolocation configuration and URL expansion.

OpenClaw parity: mirrors extensions/geolocation/src/config.ts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict

DEFAULT_DATABASE_URL = "https://download.db-ip.com/free/dbip-city-lite-{yyyy}-{mm}.mmdb.gz"
DEFAULT_ATTRIBUTION_TEXT = "IP Geolocation by DB-IP"
DEFAULT_ATTRIBUTION_URL = "https://db-ip.com"
DEFAULT_REFRESH_DAYS = 30


class GeolocationAttribution(TypedDict):
    text: str
    url: str


class GeolocationSettings(TypedDict):
    databaseUrl: str
    attribution: GeolocationAttribution
    refreshMs: int


def positive_refresh_days(value: Any) -> int | None:
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    return None


def normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed if trimmed else None
    return None


def resolve_geolocation_settings(plugin_config: Any) -> GeolocationSettings:
    config = plugin_config if isinstance(plugin_config, dict) else {}
    refresh_days = positive_refresh_days(config.get("refreshDays"))
    if refresh_days is None:
        refresh_days = DEFAULT_REFRESH_DAYS
    return {
        "databaseUrl": normalize_optional_string(config.get("databaseUrl")) or DEFAULT_DATABASE_URL,
        "attribution": {
            "text": normalize_optional_string(config.get("attributionText"))
            or DEFAULT_ATTRIBUTION_TEXT,
            "url": normalize_optional_string(config.get("attributionUrl"))
            or DEFAULT_ATTRIBUTION_URL,
        },
        "refreshMs": refresh_days * 24 * 60 * 60 * 1000,
    }


def expand_database_urls(template: str, now: datetime | None = None) -> list[str]:
    """Monthly builds appear a few days into the month, so the newest published
    release is either this month's or the previous one. Callers try in order.
    """
    dt = now or datetime.now(UTC)
    if dt.month == 1:
        prev_year = dt.year - 1
        prev_month = 12
    else:
        prev_year = dt.year
        prev_month = dt.month - 1

    candidates = [(dt.year, dt.month), (prev_year, prev_month)]
    urls: list[str] = []
    for y, m in candidates:
        url = template.replace("{yyyy}", f"{y:04d}").replace("{mm}", f"{m:02d}")
        if url not in urls:
            urls.append(url)
    return urls
