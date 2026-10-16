"""Google Meet transport types and dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GOOGLE_MEET_TRANSCRIPT_MAX_LINES = 2000

GoogleMeetManualActionReason = Literal[
    "google-login-required",
    "meet-admission-required",
    "meet-permission-required",
    "meet-audio-choice-required",
    "meet-locale-required",
    "meet-session-conflict",
    "browser-control-unavailable",
]

GoogleMeetSpeechBlockedReason = Literal[
    "google-login-required",
    "meet-admission-required",
    "meet-permission-required",
    "meet-audio-choice-required",
    "meet-locale-required",
    "meet-session-conflict",
    "browser-control-unavailable",
    "not-in-call",
    "browser-unverified",
    "audio-bridge-unavailable",
    "meet-microphone-muted",
]


@dataclass(slots=True)
class GoogleMeetManualAction:
    reason: str
    message: str


@dataclass(slots=True)
class GoogleMeetChromeHealth:
    in_call: bool = False
    inCall: bool = False
    browser_url: str | None = None
    browserUrl: str | None = None
    browser_title: str | None = None
    browserTitle: str | None = None
    microphone_muted: bool | None = None
    microphoneMuted: bool | None = None
    audio_input_routed: bool | None = None
    audioInputRouted: bool | None = None
    audio_input_device_label: str | None = None
    audioInputDeviceLabel: str | None = None
    audio_output_routed: bool | None = None
    audioOutputRouted: bool | None = None
    audio_output_device_label: str | None = None
    audioOutputDeviceLabel: str | None = None
    manual_action: GoogleMeetManualAction | None = None
    manualAction: dict[str, Any] | None = None
    speech_blocked_reason: str | None = None
    speechBlockedReason: str | None = None
    transcript_lines: int = 0
    transcriptLines: int = 0
    last_caption_text: str | None = None
    lastCaptionText: str | None = None
    last_caption_speaker: str | None = None
    lastCaptionSpeaker: str | None = None
    last_caption_at: str | None = None
    lastCaptionAt: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GoogleMeetBrowserTab:
    node_id: str | None = None
    nodeId: str | None = None
    target_id: str | None = None
    targetId: str | None = None
    url: str | None = None
    title: str | None = None


GoogleMeetBrowserCandidateTab = GoogleMeetBrowserTab


@dataclass(slots=True)
class GoogleMeetTranscriptLine:
    speaker: str | None = None
    text: str = ""
    timestamp: str | None = None
    index: int = 0


@dataclass(slots=True)
class GoogleMeetTranscriptSnapshot:
    lines: list[dict[str, Any]] = field(default_factory=list)
    next_index: int = 0
    nextIndex: int = 0


@dataclass(slots=True)
class GoogleMeetJoinRequest:
    url: str = ""
    transport: str | None = None
    mode: str | None = None
    agent_id: str | None = None
    agentId: str | None = None
    message: str | None = None
    dial_in_number: str | None = None
    dialInNumber: str | None = None
    pin: str | None = None
    dtmf_sequence: str | None = None
    dtmfSequence: str | None = None
    requester_session_key: str | None = None
    requesterSessionKey: str | None = None


@dataclass(slots=True)
class GoogleMeetTwilioState:
    dial_in_number: str
    pin_provided: bool = False
    dtmf_sequence: str | None = None
    voice_call_id: str | None = None
    dtmf_sent: bool = False
    intro_sent: bool = False


@dataclass(slots=True)
class GoogleMeetSession:
    id: str
    url: str
    transport: str
    mode: str
    agent_id: str = "main"
    created_at: str = ""
    createdAt: str = ""
    status: str = "joining"
    chrome: dict[str, Any] | None = None
    twilio: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    transcript: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class GoogleMeetJoinResult:
    session: GoogleMeetJoinResultSession
    reused: bool = False


@dataclass(slots=True)
class GoogleMeetJoinResultSession:
    id: str
    url: str
    transport: str
    mode: str
    agent_id: str = "main"


@dataclass(slots=True)
class GoogleMeetChromeSession:
    browser_profile: str | None = None
    node_id: str | None = None
    target_id: str | None = None
    url: str | None = None
    tab: GoogleMeetBrowserTab | None = None
    health: GoogleMeetChromeHealth | None = None


GoogleMeetTwilioSession = GoogleMeetTwilioState
