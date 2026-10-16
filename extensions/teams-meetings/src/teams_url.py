"""Teams Meetings URL validation, categorization, and normalization."""

from __future__ import annotations

import urllib.parse

WORK_TEAMS_HOSTS = ("teams.microsoft.com", "teams.cloud.microsoft")
CONSUMER_TEAMS_HOSTS = ("teams.live.com",)


def is_work_teams_host(host: str) -> bool:
    h = host.lower()
    return any(h == wh or h.endswith(f".{wh}") for wh in WORK_TEAMS_HOSTS)


def is_consumer_teams_host(host: str) -> bool:
    h = host.lower()
    return any(h == ch or h.endswith(f".{ch}") for ch in CONSUMER_TEAMS_HOSTS)


def is_valid_teams_host(host: str) -> bool:
    return is_work_teams_host(host) or is_consumer_teams_host(host)


def normalize_teams_url(raw_url: str | None) -> str:
    if not raw_url or not str(raw_url).strip():
        raise ValueError("Teams meeting URL is required")
    url_str = str(raw_url).strip()
    if not url_str.startswith("http://") and not url_str.startswith("https://"):
        url_str = f"https://{url_str}"
    try:
        parsed = urllib.parse.urlparse(url_str)
    except Exception as err:
        raise ValueError(f"Invalid Teams meeting URL: {raw_url}") from err

    host = (parsed.hostname or "").lower()
    if not is_valid_teams_host(host):
        raise ValueError(
            f"Unsupported Teams meeting host '{host}'. Supported hosts: {', '.join(WORK_TEAMS_HOSTS + CONSUMER_TEAMS_HOSTS)}"
        )

    path = parsed.path or "/"
    if is_work_teams_host(host):
        if not path.startswith("/l/meetup-join") and "/meetup-join/" not in path:
            raise ValueError(
                f"Invalid Teams work meeting URL path '{path}'. Expected path starting with /l/meetup-join/"
            )
    elif is_consumer_teams_host(host):
        if not path.startswith("/meet") and "/meet/" not in path:
            raise ValueError(
                f"Invalid Teams consumer meeting URL path '{path}'. Expected path starting with /meet/"
            )

    return urllib.parse.urlunparse(
        (
            "https",
            host + (f":{parsed.port}" if parsed.port and parsed.port != 443 else ""),
            path,
            parsed.params,
            parsed.query,
            "",
        )
    )


def is_work_teams_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(str(url).strip())
        return is_work_teams_host(parsed.hostname or "")
    except Exception:
        return False


def is_consumer_teams_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urllib.parse.urlparse(str(url).strip())
        return is_consumer_teams_host(parsed.hostname or "")
    except Exception:
        return False
