"""jarvis.plugins.zoom_meetings — Zoom Meetings plugin configuration & URL parsing.

OpenClaw parity: mirrors
``openclaw-main/extensions/zoom-meetings/src/config.ts`` and
``openclaw-main/extensions/zoom-meetings/src/transports/zoom-meetings-urls.ts``.

Features:
- `ZOOM_MEETINGS_TOOL_ACTIONS`: `join`, `leave`, `status`, `transcript`, `speak`.
- `is_valid_zoom_meeting_url()`: Validates Zoom meeting links (`zoom.us/j/...` and subdomains).
- `ZoomMeetingsConfig`: Dataclass containing plugin configuration settings.
- `resolve_zoom_meetings_config()`: Resolves and defaults Zoom Meetings plugin options.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

ZOOM_MEETINGS_TOOL_ACTIONS: list[str] = [
    "join",
    "leave",
    "status",
    "transcript",
    "speak",
]

_ZOOM_INVITATION_REGEX = re.compile(r"^/j/(\d{9,11})/?$")
_ZOOM_WC_REGEX = re.compile(r"^/wc/(\d{9,11})/join/?$")


@dataclass
class ZoomMeetingsChromeConfig:
    guestName: str = "OpenClaw Agent"
    autoJoin: bool = True
    reuseExistingTab: bool = True
    waitForInCallMs: int = 20_000


@dataclass
class ZoomMeetingsConfig:
    enabled: bool = True
    defaultMode: str = "agent"
    chrome: ZoomMeetingsChromeConfig = field(default_factory=ZoomMeetingsChromeConfig)
    chrome_node_id: str | None = None


def is_valid_zoom_meeting_url(url: str) -> bool:
    """Validate if a string is a valid Zoom meeting URL."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            return False

        host = parsed.hostname.lower()
        if not (host == "zoom.us" or host.endswith(".zoom.us")):
            return False

        if _ZOOM_INVITATION_REGEX.match(parsed.path):
            return True
        if host == "app.zoom.us" and _ZOOM_WC_REGEX.match(parsed.path):
            return True

        return False
    except Exception:
        return False


def resolve_zoom_meetings_config(plugin_cfg: dict[str, Any] | None) -> ZoomMeetingsConfig:
    """Resolve Zoom Meetings plugin options from configuration dictionary."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}

    raw_mode = str(val.get("defaultMode") or "agent").lower()
    mode = raw_mode if raw_mode in ("agent", "bidi", "transcribe") else "agent"

    chrome_cfg = ZoomMeetingsChromeConfig()
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

    return ZoomMeetingsConfig(
        enabled=bool(val.get("enabled", True)),
        defaultMode=mode,
        chrome=chrome_cfg,
        chrome_node_id=node_id,
    )


__all__ = [
    "ZOOM_MEETINGS_TOOL_ACTIONS",
    "ZoomMeetingsChromeConfig",
    "ZoomMeetingsConfig",
    "is_valid_zoom_meeting_url",
    "resolve_zoom_meetings_config",
]
