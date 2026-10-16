"""jarvis.plugins.google_meet — Google Meet plugin configuration, transports & tool action contracts.

OpenClaw parity: mirrors
``openclaw-main/extensions/google-meet/src/config.ts`` and
``openclaw-main/extensions/google-meet/src/meet-url.ts``.

Features:
- `GoogleMeetTransport`: `"chrome"` | `"chrome-node"` | `"twilio"`
- `GoogleMeetMode`: `"agent"` | `"bidi"` | `"transcribe"`
- `GoogleMeetAccessType`: `"OPEN"` | `"TRUSTED"` | `"RESTRICTED"`
- `GOOGLE_MEET_TOOL_ACTIONS`: List of supported actions for the `google_meet` tool.
- `GoogleMeetConfig`: Dataclass containing plugin configuration settings.
- `resolve_google_meet_config()`: Resolves and defaults Google Meet plugin options.
- `is_valid_meet_url()`: Helper for validating Meet URLs (`https://meet.google.com/...`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

GoogleMeetTransport = Literal["chrome", "chrome-node", "twilio"]
GoogleMeetMode = Literal["agent", "bidi", "transcribe"]
GoogleMeetAccessType = Literal["OPEN", "TRUSTED", "RESTRICTED"]

GOOGLE_MEET_TOOL_ACTIONS: list[str] = [
    "join",
    "create",
    "status",
    "setup_status",
    "resolve_space",
    "preflight",
    "latest",
    "calendar_events",
    "artifacts",
    "attendance",
    "export",
    "recover_current_tab",
    "transcript",
    "leave",
    "end_active_conference",
    "speak",
    "test_speech",
    "test_listen",
]

_MEET_URL_REGEX = re.compile(r"^https://meet\.google\.com/[a-z0-9\-]+$", re.IGNORECASE)


@dataclass
class GoogleMeetChromeConfig:
    guestName: str = "OpenClaw Agent"
    autoJoin: bool = True
    reuseExistingTab: bool = True
    waitForInCallMs: int = 20_000
    audioBackend: str = "blackhole-2ch"


@dataclass
class GoogleMeetConfig:
    enabled: bool = True
    defaultTransport: GoogleMeetTransport = "chrome"
    defaultMode: GoogleMeetMode = "agent"
    chrome: GoogleMeetChromeConfig = field(default_factory=GoogleMeetChromeConfig)
    chrome_node_id: str | None = None
    voice_call_enabled: bool = True


def is_valid_meet_url(url: str) -> bool:
    """Validate if a string is a valid Google Meet URL."""
    if not url or not isinstance(url, str):
        return False
    return bool(_MEET_URL_REGEX.match(url.strip()))


def resolve_google_meet_config(plugin_cfg: dict[str, Any] | None) -> GoogleMeetConfig:
    """Resolve Google Meet plugin options from configuration dictionary."""
    val = plugin_cfg if isinstance(plugin_cfg, dict) else {}

    raw_transport = str(val.get("defaultTransport") or "chrome").lower()
    transport: GoogleMeetTransport = (
        raw_transport if raw_transport in ("chrome", "chrome-node", "twilio") else "chrome"  # type: ignore[assignment]
    )

    raw_mode = str(val.get("defaultMode") or "agent").lower()
    if raw_mode == "realtime":
        raw_mode = "agent"
    mode: GoogleMeetMode = raw_mode if raw_mode in ("agent", "bidi", "transcribe") else "agent"  # type: ignore[assignment]

    chrome_cfg = GoogleMeetChromeConfig()
    raw_chrome = val.get("chrome")
    if isinstance(raw_chrome, dict):
        chrome_cfg.guestName = str(raw_chrome.get("guestName") or "OpenClaw Agent")
        chrome_cfg.autoJoin = bool(raw_chrome.get("autoJoin", True))
        chrome_cfg.reuseExistingTab = bool(raw_chrome.get("reuseExistingTab", True))
        chrome_cfg.waitForInCallMs = int(raw_chrome.get("waitForInCallMs", 20_000))
        chrome_cfg.audioBackend = str(raw_chrome.get("audioBackend") or "blackhole-2ch")

    node_id: str | None = None
    raw_node = val.get("chromeNode")
    if isinstance(raw_node, dict) and isinstance(raw_node.get("node"), str):
        node_id = raw_node["node"].strip() or None

    return GoogleMeetConfig(
        enabled=bool(val.get("enabled", True)),
        defaultTransport=transport,
        defaultMode=mode,
        chrome=chrome_cfg,
        chrome_node_id=node_id,
        voice_call_enabled=bool(val.get("voiceCall", {}).get("enabled", True)),
    )


__all__ = [
    "GOOGLE_MEET_TOOL_ACTIONS",
    "GoogleMeetAccessType",
    "GoogleMeetChromeConfig",
    "GoogleMeetConfig",
    "GoogleMeetMode",
    "GoogleMeetTransport",
    "is_valid_meet_url",
    "resolve_google_meet_config",
]
