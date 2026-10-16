"""jarvis.plugins.teams_meetings — Microsoft Teams Meetings plugin configuration & URL parsing.

OpenClaw parity: mirrors
``openclaw-main/extensions/teams-meetings/src/config.ts`` and
``openclaw-main/extensions/teams-meetings/src/transports/teams-meetings-urls.ts``.

Features:
- `TEAMS_MEETINGS_TOOL_ACTIONS`: `join`, `leave`, `status`, `transcript`, `speak`.
- `is_valid_teams_meeting_url()`: Validates Microsoft Teams meeting links (work & consumer).
- `TeamsMeetingsConfig`: Dataclass containing plugin configuration settings.
- `resolve_teams_meetings_config()`: Resolves and defaults Teams Meetings plugin options.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse

TEAMS_MEETINGS_TOOL_ACTIONS: list[str] = [
    "join",
    "leave",
    "status",
    "transcript",
    "speak",
]

_WORK_MEETUP_REGEX = re.compile(r"^/l/meetup-join/([^/]+)", re.IGNORECASE)
_CONSUMER_MEET_REGEX = re.compile(r"^/meet/([^/]+)", re.IGNORECASE)


@dataclass
class TeamsMeetingsChromeConfig:
    guestName: str = "OpenClaw Agent"
    autoJoin: bool = True
    reuseExistingTab: bool = True
    waitForInCallMs: int = 20_000


@dataclass
class TeamsMeetingsConfig:
    enabled: bool = True
    defaultMode: str = "agent"
    chrome: TeamsMeetingsChromeConfig = field(default_factory=TeamsMeetingsChromeConfig)
    chrome_node_id: str | None = None


def is_valid_teams_meeting_url(url: str) -> bool:
    """Validate if a string is a valid Microsoft Teams work or consumer meeting URL."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            return False

        host = parsed.hostname.lower()

        # Work links: teams.microsoft.com/l/meetup-join/...
        if host == "teams.microsoft.com":
            match = _WORK_MEETUP_REGEX.match(parsed.path)
            if match:
                thread_id = unquote(match.group(1))
                return bool(re.match(r"^19:[^/]+@thread\.(?:v2|tacv2)$", thread_id, re.IGNORECASE))

        # Consumer links: teams.live.com/meet/...
        if host == "teams.live.com":
            if parsed.path.lower().startswith("/meet/") or parsed.path.lower().startswith("/dl/launcher/"):
                return True

        return False
    except Exception:
        return False


def resolve_teams_meetings_config(plugin_cfg: dict[str, Any] | None) -> TeamsMeetingsConfig:
    """Resolve Microsoft Teams Meetings plugin options from configuration dictionary."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}

    raw_mode = str(val.get("defaultMode") or "agent").lower()
    mode = raw_mode if raw_mode in ("agent", "bidi", "transcribe") else "agent"

    chrome_cfg = TeamsMeetingsChromeConfig()
    raw_chrome = val.get("chrome")
    if isinstance(raw_chrome, dict):
        chrome_cfg.guestName = str(raw_chrome.get("guestName") or "OpenClaw Agent")
        chrome_cfg.autoJoin = bool(raw_chrome.get("autoJoin", True))
        chrome_cfg.reuseExistingTab = bool(raw_chrome.get("reuseExistingTab", True))
        chrome_cfg.waitForInCallMs = int(raw_chrome.get("waitForInCallMs", 20_000))

    node_id: str | None = None
    raw_node = val.get("chromeNode")
    if isinstance(raw_node, dict) and isinstance(raw_node.get("node"), str):
        node_id = raw_node["node"].strip() or None

    return TeamsMeetingsConfig(
        enabled=bool(val.get("enabled", True)),
        defaultMode=mode,
        chrome=chrome_cfg,
        chrome_node_id=node_id,
    )


__all__ = [
    "TEAMS_MEETINGS_TOOL_ACTIONS",
    "TeamsMeetingsChromeConfig",
    "TeamsMeetingsConfig",
    "is_valid_teams_meeting_url",
    "resolve_teams_meetings_config",
]
