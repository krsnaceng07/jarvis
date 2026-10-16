"""Teams Meetings transport types and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TEAMS_MEETINGS_TRANSCRIPT_MAX_LINES = 2000

TeamsMeetingsManualActionReason = Literal[
    "teams-login-required",
    "teams-verification-required",
    "teams-admission-required",
    "teams-permission-required",
    "teams-audio-choice-required",
    "teams-locale-required",
    "teams-session-conflict",
    "browser-control-unavailable",
]

TeamsMeetingsSpeechBlockedReason = Literal[
    "teams-login-required",
    "teams-verification-required",
    "teams-admission-required",
    "teams-permission-required",
    "teams-audio-choice-required",
    "teams-locale-required",
    "teams-session-conflict",
    "browser-control-unavailable",
    "not-in-call",
    "browser-unverified",
    "audio-bridge-unavailable",
    "teams-microphone-muted",
]


@dataclass(slots=True)
class TeamsMeetingsManualAction:
    reason: str
    message: str
    category: str = "custom"


@dataclass(slots=True)
class TeamsMeetingsTranscriptLine:
    speaker: str | None = None
    text: str = ""
    timestamp: str | None = None
    at: str | None = None
    index: int = 0


@dataclass(slots=True)
class TeamsMeetingsTranscriptSnapshot:
    lines: list[TeamsMeetingsTranscriptLine] = field(default_factory=list)
    dropped_lines: int = 0
    epoch: str | None = None
    url_matched: bool | None = None
    session_matched: bool | None = None
    next_index: int = 0
    nextIndex: int = 0


@dataclass(slots=True)
class TeamsMeetingsBrowserTab:
    node_id: str | None = None
    nodeId: str | None = None
    target_id: str | None = None
    targetId: str | None = None
    url: str | None = None
    title: str | None = None


TeamsMeetingsBrowserCandidateTab = TeamsMeetingsBrowserTab


@dataclass(slots=True)
class TeamsMeetingsChromeHealth:
    in_call: bool = False
    inCall: bool = False
    mic_muted: bool | None = None
    micMuted: bool | None = None
    camera_off: bool | None = None
    cameraOff: bool | None = None
    lobby_waiting: bool | None = None
    lobbyWaiting: bool | None = None
    captioning: bool | None = None
    captions_enabled_attempted: bool | None = None
    captionsEnabledAttempted: bool | None = None
    transcript_lines: int = 0
    transcriptLines: int = 0
    last_caption_text: str | None = None
    lastCaptionText: str | None = None
    last_caption_speaker: str | None = None
    lastCaptionSpeaker: str | None = None
    last_caption_at: str | None = None
    lastCaptionAt: str | None = None
    recent_transcript: list[TeamsMeetingsTranscriptLine] | None = None
    audio_input_routed: bool | None = None
    audioInputRouted: bool | None = None
    audio_input_device_label: str | None = None
    audioInputDeviceLabel: str | None = None
    audio_input_route_error: str | None = None
    audio_output_routed: bool | None = None
    audioOutputRouted: bool | None = None
    audio_output_device_label: str | None = None
    audioOutputDeviceLabel: str | None = None
    audio_output_route_error: str | None = None
    manual_action: TeamsMeetingsManualAction | None = None
    manualAction: dict[str, Any] | None = None
    speech_blocked_reason: str | None = None
    speechBlockedReason: str | None = None
    browser_url: str | None = None
    browserUrl: str | None = None
    browser_title: str | None = None
    browserTitle: str | None = None
    leave_reason: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TeamsMeetingsJoinRequest:
    url: str = ""
    transport: str | None = None
    mode: str | None = None
    agent_id: str | None = None
    agentId: str | None = None
    message: str | None = None
    audio_in: str | None = None
    audio_out: str | None = None
    profile: str | None = None
    node: str | None = None
    node_id: str | None = None
    requester_session_key: str | None = None
    requesterSessionKey: str | None = None


@dataclass(slots=True)
class TeamsMeetingsChromeSession:
    browser_profile: str | None = None
    node_id: str | None = None
    target_id: str | None = None
    url: str | None = None
    browser_tab: TeamsMeetingsBrowserTab | None = None
    health: TeamsMeetingsChromeHealth | None = None
    audio_backend: str | None = None
    launched: bool = False


@dataclass(slots=True)
class TeamsMeetingsSession:
    id: str
    url: str
    transport: str
    mode: str
    agent_id: str = "main"
    state: str = "active"
    status: str = "active"
    created_at: str = ""
    createdAt: str = ""
    updated_at: str = ""
    ended_at: str | None = None
    browser_left: bool | None = None
    chrome: TeamsMeetingsChromeSession | None = None
    notes: list[str] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class TeamsMeetingsJoinResultSession:
    id: str
    url: str
    transport: str
    mode: str
    agent_id: str = "main"


@dataclass(slots=True)
class TeamsMeetingsJoinResult:
    session: TeamsMeetingsSession | TeamsMeetingsJoinResultSession
    reused: bool = False
    spoken: bool = False
