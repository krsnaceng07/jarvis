"""Configuration definitions and resolver for the Zoom Meetings plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Err, Ok, Result


@dataclass(slots=True)
class ZoomMeetingsChromeConfig:
    launch: bool = True
    auto_join: bool = True
    guest_name: str = "JARVIS"
    reuse_existing_tab: bool = True
    audio_backend: str = "auto"
    audio_format: str = "pcm_s16le"
    audio_input_command: list[str] = field(default_factory=list)
    audio_output_command: list[str] = field(default_factory=list)
    barge_in_input_command: list[str] = field(default_factory=list)
    audio_bridge_command: list[str] = field(default_factory=list)
    join_timeout_ms: int = 30000
    wait_for_in_call_ms: int = 5000
    browser_profile: str | None = None
    grant_media_permissions: bool = True
    passcode: str | None = None


@dataclass(slots=True)
class ZoomMeetingsChromeNodeConfig:
    node: str | None = None


@dataclass(slots=True)
class ZoomMeetingsRealtimeConfig:
    agent_id: str | None = None
    intro_message: str = "Hello, I am JARVIS, joining this Zoom meeting."


@dataclass(slots=True)
class ZoomMeetingsDefaultsConfig:
    meeting: str | None = None


@dataclass(slots=True)
class ZoomMeetingsConfig:
    enabled: bool = True
    default_transport: str = "chrome"  # "chrome" | "chrome-node"
    default_mode: str = "agent"  # "agent" | "bidi" | "listen" | "transcribe"
    chrome: ZoomMeetingsChromeConfig = field(default_factory=ZoomMeetingsChromeConfig)
    chrome_node: ZoomMeetingsChromeNodeConfig = field(default_factory=ZoomMeetingsChromeNodeConfig)
    realtime: ZoomMeetingsRealtimeConfig = field(default_factory=ZoomMeetingsRealtimeConfig)
    defaults: ZoomMeetingsDefaultsConfig = field(default_factory=ZoomMeetingsDefaultsConfig)


def resolve_zoom_meetings_config(
    raw_config: dict[str, Any] | None,
) -> Result[ZoomMeetingsConfig, str]:
    """Parse and validate raw plugin configuration dictionary."""
    if not raw_config:
        return Ok(ZoomMeetingsConfig())

    try:
        enabled = bool(raw_config.get("enabled", True))
        def_trans = str(raw_config.get("defaultTransport", "chrome") or "chrome").lower()
        if def_trans not in ("chrome", "chrome-node"):
            return Err(
                f"Invalid defaultTransport '{def_trans}'. Must be 'chrome' or 'chrome-node'."
            )

        def_mode = str(raw_config.get("defaultMode", "agent") or "agent").lower()
        if def_mode not in ("agent", "bidi", "listen", "transcribe"):
            return Err(
                f"Invalid defaultMode '{def_mode}'. Must be 'agent', 'bidi', 'listen', or 'transcribe'."
            )

        # Parse chrome sub-config
        raw_chrome = raw_config.get("chrome") or {}
        chrome_cfg = ZoomMeetingsChromeConfig(
            launch=bool(raw_chrome.get("launch", True)),
            auto_join=bool(raw_chrome.get("autoJoin", True)),
            guest_name=str(raw_chrome.get("guestName") or "JARVIS"),
            reuse_existing_tab=bool(raw_chrome.get("reuseExistingTab", True)),
            audio_backend=str(raw_chrome.get("audioBackend", "auto") or "auto"),
            audio_format=str(raw_chrome.get("audioFormat", "pcm_s16le") or "pcm_s16le"),
            audio_input_command=list(raw_chrome.get("audioInputCommand") or []),
            audio_output_command=list(raw_chrome.get("audioOutputCommand") or []),
            barge_in_input_command=list(raw_chrome.get("bargeInInputCommand") or []),
            audio_bridge_command=list(raw_chrome.get("audioBridgeCommand") or []),
            join_timeout_ms=int(raw_chrome.get("joinTimeoutMs", 30000) or 30000),
            wait_for_in_call_ms=int(raw_chrome.get("waitForInCallMs", 5000) or 5000),
            browser_profile=raw_chrome.get("browserProfile"),
            grant_media_permissions=bool(raw_chrome.get("grantMediaPermissions", True)),
            passcode=raw_chrome.get("passcode") or raw_chrome.get("meetingPasscode"),
        )

        # Parse chrome-node sub-config
        raw_cn = raw_config.get("chromeNode") or {}
        cn_cfg = ZoomMeetingsChromeNodeConfig(node=raw_cn.get("node"))

        # Parse realtime sub-config
        raw_rt = raw_config.get("realtime") or {}
        rt_cfg = ZoomMeetingsRealtimeConfig(
            agent_id=raw_rt.get("agentId"),
            intro_message=str(
                raw_rt.get("introMessage") or "Hello, I am JARVIS, joining this Zoom meeting."
            ),
        )

        # Parse defaults sub-config
        raw_def = raw_config.get("defaults") or {}
        def_cfg = ZoomMeetingsDefaultsConfig(meeting=raw_def.get("meeting"))

        return Ok(
            ZoomMeetingsConfig(
                enabled=enabled,
                default_transport=def_trans,
                default_mode=def_mode,
                chrome=chrome_cfg,
                chrome_node=cn_cfg,
                realtime=rt_cfg,
                defaults=def_cfg,
            )
        )
    except Exception as ex:
        return Err(f"Failed to parse Zoom Meetings configuration: {ex}")
