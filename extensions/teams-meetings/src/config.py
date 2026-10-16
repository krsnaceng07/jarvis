"""Configuration schema and resolution for Teams Meetings plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import Err, Ok, Result


@dataclass(slots=True)
class TeamsMeetingsChromeConfig:
    launch: bool = True
    auto_join: bool = True
    guest_name: str = "JARVIS"
    reuse_existing_tab: bool = True
    audio_backend: str = "auto"
    audio_format: str = "pcm_s16le"
    audio_input_command: list[str] | None = None
    audio_output_command: list[str] | None = None
    barge_in_input_command: list[str] | None = None
    audio_bridge_command: list[str] | None = None
    join_timeout_ms: int = 30000
    wait_for_in_call_ms: int = 5000
    browser_profile: str | None = None


@dataclass(slots=True)
class TeamsMeetingsChromeNodeConfig:
    node: str | None = None


@dataclass(slots=True)
class TeamsMeetingsRealtimeConfig:
    agent_id: str | None = None
    intro_message: str = "Hello, I am JARVIS, joining this Teams meeting."


@dataclass(slots=True)
class TeamsMeetingsDefaultsConfig:
    meeting: str | None = None


@dataclass(slots=True)
class TeamsMeetingsConfig:
    enabled: bool = True
    default_transport: str = "chrome"
    default_mode: str = "agent"
    chrome: TeamsMeetingsChromeConfig = field(default_factory=TeamsMeetingsChromeConfig)
    chrome_node: TeamsMeetingsChromeNodeConfig = field(
        default_factory=TeamsMeetingsChromeNodeConfig
    )
    realtime: TeamsMeetingsRealtimeConfig = field(default_factory=TeamsMeetingsRealtimeConfig)
    defaults: TeamsMeetingsDefaultsConfig = field(default_factory=TeamsMeetingsDefaultsConfig)


def resolve_teams_meetings_config(
    raw: dict[str, Any] | None = None,
) -> Result[TeamsMeetingsConfig, str]:
    data = raw or {}
    try:
        chrome_raw = data.get("chrome") if isinstance(data.get("chrome"), dict) else {}
        node_raw = (
            data.get("chromeNode")
            if isinstance(data.get("chromeNode"), dict)
            else (data.get("chrome_node") if isinstance(data.get("chrome_node"), dict) else {})
        )
        realtime_raw = data.get("realtime") if isinstance(data.get("realtime"), dict) else {}
        defaults_raw = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}

        chrome = TeamsMeetingsChromeConfig(
            launch=chrome_raw.get("launch", True),
            auto_join=chrome_raw.get("autoJoin", chrome_raw.get("auto_join", True)),
            guest_name=chrome_raw.get("guestName", chrome_raw.get("guest_name", "JARVIS")),
            reuse_existing_tab=chrome_raw.get(
                "reuseExistingTab", chrome_raw.get("reuse_existing_tab", True)
            ),
            audio_backend=chrome_raw.get("audioBackend", chrome_raw.get("audio_backend", "auto")),
            audio_format=chrome_raw.get("audioFormat", chrome_raw.get("audio_format", "pcm_s16le")),
            audio_input_command=chrome_raw.get(
                "audioInputCommand", chrome_raw.get("audio_input_command")
            ),
            audio_output_command=chrome_raw.get(
                "audioOutputCommand", chrome_raw.get("audio_output_command")
            ),
            barge_in_input_command=chrome_raw.get(
                "bargeInInputCommand", chrome_raw.get("barge_in_input_command")
            ),
            audio_bridge_command=chrome_raw.get(
                "audioBridgeCommand", chrome_raw.get("audio_bridge_command")
            ),
            join_timeout_ms=int(
                chrome_raw.get("joinTimeoutMs", chrome_raw.get("join_timeout_ms", 30000))
            ),
            wait_for_in_call_ms=int(
                chrome_raw.get("waitForInCallMs", chrome_raw.get("wait_for_in_call_ms", 5000))
            ),
            browser_profile=chrome_raw.get("browserProfile", chrome_raw.get("browser_profile")),
        )

        chrome_node = TeamsMeetingsChromeNodeConfig(node=node_raw.get("node"))

        realtime = TeamsMeetingsRealtimeConfig(
            agent_id=realtime_raw.get("agentId", realtime_raw.get("agent_id")),
            intro_message=realtime_raw.get(
                "introMessage",
                realtime_raw.get(
                    "intro_message", "Hello, I am JARVIS, joining this Teams meeting."
                ),
            ),
        )

        defaults = TeamsMeetingsDefaultsConfig(meeting=defaults_raw.get("meeting"))

        return Ok(
            TeamsMeetingsConfig(
                enabled=data.get("enabled", True),
                default_transport=data.get(
                    "defaultTransport", data.get("default_transport", "chrome")
                ),
                default_mode=data.get("defaultMode", data.get("default_mode", "agent")),
                chrome=chrome,
                chrome_node=chrome_node,
                realtime=realtime,
                defaults=defaults,
            )
        )
    except Exception as err:
        return Err(f"Invalid Teams Meetings configuration: {err}")
