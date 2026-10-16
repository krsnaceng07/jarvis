"""Google Meet adapter: platform URL, DOM, wire-value, and manual-action ownership."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ..meet_url import normalize_meet_url
from .google_meet_page_scripts import (
    meet_leave_script,
    meet_status_script,
    meet_transcript_script,
)
from .google_meet_platform_constants import GOOGLE_MEET_NODE_COMMAND
from .google_meet_urls import (
    force_meet_english_ui,
    is_english_meet_tab,
    is_recoverable_meet_tab,
    is_same_meet_url_for_reuse,
    normalize_meet_url_for_reuse,
    read_meet_auth_user,
)
from .twilio import (
    build_meet_dtmf_sequence,
    normalize_dial_in_number,
    prefix_dtmf_wait,
)
from .types import (
    GoogleMeetBrowserCandidateTab,
    GoogleMeetChromeHealth,
    GoogleMeetManualAction,
    GoogleMeetTranscriptLine,
    GoogleMeetTranscriptSnapshot,
)

MANUAL_ACTION_CATEGORIES: dict[str, str] = {
    "browser-control-unavailable": "browser-control-unavailable",
    "google-login-required": "login-required",
    "meet-admission-required": "admission-required",
    "meet-audio-choice-required": "audio-choice-required",
    "meet-locale-required": "locale-required",
    "meet-permission-required": "permission-required",
    "meet-session-conflict": "session-conflict",
}


def classify_manual_action_reason(reason: str) -> str:
    return MANUAL_ACTION_CATEGORIES.get(reason, "custom")


def is_talk_back_mode(mode: str) -> bool:
    return mode in ("agent", "bidi")


def is_realtime_route_ready(mode: str, health: GoogleMeetChromeHealth | None) -> bool:
    if not is_talk_back_mode(mode):
        return True
    if not health:
        return False
    return health.in_call is True and health.mic_muted is not True


def parse_permission_grant_notes(result: Any) -> list[str]:
    record = result if isinstance(result, dict) else {}
    unsupported_permissions = [
        str(v) for v in record.get("unsupportedPermissions", []) if isinstance(v, str)
    ]
    notes = ["Granted Meet microphone/camera permissions through browser control."]
    if "speakerSelection" in unsupported_permissions:
        notes.append("Chrome did not accept the optional Meet speaker-selection permission.")
    return notes


def browser_result_string(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    val = result.get("result")
    if isinstance(val, str) and val.strip():
        return val
    return None


def parse_meeting_browser_status(result: Any) -> GoogleMeetChromeHealth | None:
    raw = browser_result_string(result)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception as err:
        raise ValueError("Google Meet browser status JSON is malformed.") from err

    if not isinstance(parsed, dict):
        raise ValueError("Google Meet browser status JSON is malformed.")

    manual_action: GoogleMeetManualAction | None = None
    if isinstance(parsed.get("manualAction"), dict):
        ma_raw = parsed["manualAction"]
        reason = str(ma_raw.get("reason", ""))
        message = str(ma_raw.get("message", ""))
        manual_action = GoogleMeetManualAction(
            reason=reason,
            message=message,
            category=classify_manual_action_reason(reason),
        )

    recent_transcript: list[GoogleMeetTranscriptLine] = []
    if isinstance(parsed.get("recentTranscript"), list):
        for item in parsed["recentTranscript"]:
            if isinstance(item, dict) and item.get("text"):
                text = str(item["text"]).strip()
                if text:
                    recent_transcript.append(
                        GoogleMeetTranscriptLine(
                            text=text,
                            speaker=str(item.get("speaker"))
                            if item.get("speaker") is not None
                            else None,
                            at=str(item.get("at")) if item.get("at") is not None else None,
                        )
                    )

    notes = [str(n) for n in parsed.get("notes", []) if isinstance(n, str)]

    return GoogleMeetChromeHealth(
        in_call=parsed.get("inCall"),
        mic_muted=parsed.get("micMuted"),
        camera_off=parsed.get("cameraOff"),
        lobby_waiting=parsed.get("lobbyWaiting"),
        caption_capture_requested=parsed.get("captionCaptureRequested"),
        captioning=parsed.get("captioning"),
        captions_enabled_attempted=parsed.get("captionsEnabledAttempted"),
        transcript_lines=parsed.get("transcriptLines"),
        last_caption_at=parsed.get("lastCaptionAt"),
        last_caption_speaker=parsed.get("lastCaptionSpeaker"),
        last_caption_text=parsed.get("lastCaptionText"),
        recent_transcript=recent_transcript if recent_transcript else None,
        audio_input_routed=parsed.get("audioInputRouted"),
        audio_input_device_label=parsed.get("audioInputDeviceLabel"),
        audio_input_route_error=parsed.get("audioInputRouteError"),
        audio_output_routed=parsed.get("audioOutputRouted"),
        audio_output_device_label=parsed.get("audioOutputDeviceLabel"),
        audio_output_route_error=parsed.get("audioOutputRouteError"),
        audio_output_route_retryable=parsed.get("audioOutputRouteRetryable"),
        manual_action=manual_action,
        browser_url=parsed.get("url"),
        browser_title=parsed.get("title"),
        notes=notes if notes else None,
        leave_reason=parsed.get("leaveReason"),
    )


def parse_meeting_leave_result(result: Any) -> dict[str, Any]:
    raw = browser_result_string(result)
    if not raw:
        return {"departed": False}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {"departed": False}
        leave_action = (
            parsed.get("leaveAction") if parsed.get("leaveAction") in ("leave", "confirm") else None
        )
        res: dict[str, Any] = {"departed": parsed.get("departed") is True}
        if leave_action:
            res["leaveAction"] = leave_action
        if isinstance(parsed.get("sessionConflict"), bool):
            res["sessionConflict"] = parsed["sessionConflict"]
        if isinstance(parsed.get("sessionMatched"), bool):
            res["sessionMatched"] = parsed["sessionMatched"]
        if isinstance(parsed.get("urlMatched"), bool):
            res["urlMatched"] = parsed["urlMatched"]
        return res
    except Exception:
        return {"departed": False}


def parse_meeting_transcript(result: Any) -> GoogleMeetTranscriptSnapshot:
    raw = browser_result_string(result)
    if not raw:
        return GoogleMeetTranscriptSnapshot(dropped_lines=0, lines=[])
    try:
        parsed = json.loads(raw)
    except Exception as err:
        raise ValueError("Google Meet transcript JSON is malformed.") from err

    if not isinstance(parsed, dict):
        raise ValueError("Google Meet transcript payload is invalid.")

    dropped_lines = (
        int(parsed["droppedLines"])
        if isinstance(parsed.get("droppedLines"), int) and parsed["droppedLines"] >= 0
        else 0
    )
    lines: list[GoogleMeetTranscriptLine] = []
    if isinstance(parsed.get("lines"), list):
        for item in parsed["lines"]:
            if isinstance(item, dict) and item.get("text"):
                text = str(item["text"]).strip()
                if text:
                    lines.append(
                        GoogleMeetTranscriptLine(
                            text=text,
                            speaker=str(item.get("speaker"))
                            if item.get("speaker") is not None
                            else None,
                            at=str(item.get("at")) if item.get("at") is not None else None,
                        )
                    )

    epoch = str(parsed["epoch"]) if isinstance(parsed.get("epoch"), str) else None
    url_matched = parsed["urlMatched"] if isinstance(parsed.get("urlMatched"), bool) else None
    session_matched = (
        parsed["sessionMatched"] if isinstance(parsed.get("sessionMatched"), bool) else None
    )

    return GoogleMeetTranscriptSnapshot(
        dropped_lines=dropped_lines,
        lines=lines,
        epoch=epoch,
        url_matched=url_matched,
        session_matched=session_matched,
    )


@dataclass(frozen=True, slots=True)
class GoogleMeetPlatformUrls:
    validate_and_normalize: Callable[[str], str] = normalize_meet_url
    normalize_for_reuse: Callable[[str | None], str | None] = normalize_meet_url_for_reuse
    is_same_meeting: Callable[[str | None, str | None], bool] = is_same_meet_url_for_reuse
    build_join_url: Callable[[str], str] = force_meet_english_ui
    account_hint: Callable[[str | None], str | None] = read_meet_auth_user
    is_preferred_join_url: Callable[[str | None], bool] = is_english_meet_tab
    is_recoverable_tab: Callable[[GoogleMeetBrowserCandidateTab, str | None], bool] = (
        is_recoverable_meet_tab
    )

    def locale_action(self, tab: GoogleMeetBrowserCandidateTab) -> GoogleMeetManualAction | None:
        if not self.normalize_for_reuse(tab.url) or self.is_preferred_join_url(tab.url):
            return None
        return GoogleMeetManualAction(
            category="locale-required",
            reason="meet-locale-required",
            message="The existing Meet tab is not pinned to English. Open the meeting with ?hl=en, then retry recovery.",
        )


@dataclass(frozen=True, slots=True)
class GoogleMeetPlatformCaptions:
    def enabled(self, _mode: str) -> bool:
        return True

    def build_transcript_script(
        self, finalize: bool, meeting_session_id: str, meeting_url: str
    ) -> str:
        return meet_transcript_script(meeting_url, meeting_session_id, finalize)

    def parse_transcript(self, result: Any) -> GoogleMeetTranscriptSnapshot:
        return parse_meeting_transcript(result)


@dataclass(frozen=True, slots=True)
class GoogleMeetPlatformBrowser:
    captions: GoogleMeetPlatformCaptions = field(default_factory=GoogleMeetPlatformCaptions)

    def allows_microphone(self, mode: str) -> bool:
        return is_talk_back_mode(mode)

    def build_status_join_script(
        self,
        *,
        mode: str,
        auto_join: bool = False,
        capture_captions: bool = True,
        guest_name: str = "",
        read_only: bool = False,
        meeting_session_id: str = "",
        allow_session_adoption: bool = False,
        wait_for_in_call_ms: int = 0,
        url: str = "",
    ) -> str:
        return meet_status_script(
            allow_microphone=self.allows_microphone(mode),
            auto_join=auto_join,
            caption_session_id=meeting_session_id or None,
            capture_captions=capture_captions,
            guest_name=guest_name,
            read_only=read_only,
        )

    def should_retry_join_status(self, health: GoogleMeetChromeHealth) -> bool:
        return (
            health.in_call is True
            and health.manual_action is not None
            and health.manual_action.reason == "meet-audio-choice-required"
            and (health.audio_input_routed is not True or health.audio_output_routed is not True)
        )

    def browser_control_unavailable(self, _error: Any = None) -> GoogleMeetManualAction:
        return GoogleMeetManualAction(
            category="browser-control-unavailable",
            reason="browser-control-unavailable",
            message="Open the JARVIS browser profile, finish Google Meet login, admission, or permission prompts, then retry.",
        )

    def build_leave_script(self, meeting_url: str) -> str:
        return meet_leave_script(meeting_url)

    def permissions(self, allow_microphone: bool, meeting_url: str = "") -> dict[str, Any] | None:
        if allow_microphone:
            return {
                "origin": "https://meet.google.com",
                "permissions": ["audioCapture", "videoCapture"],
                "optionalPermissions": ["speakerSelection"],
            }
        return None

    def permission_notes(
        self,
        allow_microphone: bool,
        error: Any = None,
        result: Any = None,
    ) -> list[str]:
        if not allow_microphone:
            return ["Observe-only mode skips Meet microphone/camera permission grants."]
        if error:
            return [f"Could not grant Meet media permissions automatically: {error}"]
        return parse_permission_grant_notes(result)

    def parse_status(self, result: Any) -> GoogleMeetChromeHealth | None:
        return parse_meeting_browser_status(result)

    def classify_manual_action(
        self, health: GoogleMeetChromeHealth
    ) -> GoogleMeetManualAction | None:
        if not health.manual_action:
            return None
        return GoogleMeetManualAction(
            category=classify_manual_action_reason(health.manual_action.reason),
            reason=health.manual_action.reason,
            message=health.manual_action.message,
        )

    def parse_leave_result(self, result: Any) -> dict[str, Any]:
        return parse_meeting_leave_result(result)


@dataclass(frozen=True, slots=True)
class GoogleMeetPlatformDialIn:
    def build_plan(
        self,
        *,
        dial_in_number: str | None = None,
        default_dial_in_number: str | None = None,
        pin: str | None = None,
        default_pin: str | None = None,
        dtmf_sequence: str | None = None,
        default_dtmf_sequence: str | None = None,
        dtmf_delay_ms: int = 4000,
    ) -> dict[str, str | None]:
        number = normalize_dial_in_number(dial_in_number or default_dial_in_number)
        resolved_pin = pin or default_pin
        raw_dtmf = build_meet_dtmf_sequence(
            pin=resolved_pin,
            dtmf_sequence=dtmf_sequence or default_dtmf_sequence,
        )
        final_dtmf = (
            raw_dtmf
            if (dtmf_sequence or default_dtmf_sequence)
            else prefix_dtmf_wait(raw_dtmf, dtmf_delay_ms)
        )
        return {
            "number": number,
            "pin": resolved_pin,
            "dtmfSequence": final_dtmf,
        }


@dataclass(frozen=True, slots=True)
class GoogleMeetPlatformAgentConsult:
    surface: str = "a private Google Meet"
    user_label: str = "Participant"
    assistant_label: str = "Agent"
    question_source_label: str = "participant"
    working_response_label: str = "participant"
    extra_system_prompt: str = (
        "You are a behind-the-scenes consultant for a live meeting voice agent. "
        "Prioritize a fast, speakable answer over exhaustive investigation. "
        "For tool-backed status checks, prefer one or two bounded read-only queries before answering. "
        "Do not print secret values or dump environment variables; only check whether required configuration is present. "
        "Be accurate, brief, and speakable."
    )


@dataclass(frozen=True, slots=True)
class GoogleMeetPlatformSession:
    id_prefix: str = "meet"

    def participant_identity(self, transport: str) -> str:
        if transport == "twilio":
            return "Twilio phone participant"
        if transport == "chrome-node":
            return "signed-in Google Chrome profile on a paired node"
        return "signed-in Google Chrome profile"


@dataclass(frozen=True, slots=True)
class GoogleMeetPlatformAdapter:
    id: str = "google-meet"
    display_name: str = "Google Meet"
    browser_label: str = "Meet"
    log_scope: str = "[google-meet]"
    node_command_name: str = GOOGLE_MEET_NODE_COMMAND
    node_config_path: str = "plugins.entries.google-meet.config.chromeNode.node"
    agent_consult: GoogleMeetPlatformAgentConsult = field(
        default_factory=GoogleMeetPlatformAgentConsult
    )
    session: GoogleMeetPlatformSession = field(default_factory=GoogleMeetPlatformSession)
    urls: GoogleMeetPlatformUrls = field(default_factory=GoogleMeetPlatformUrls)
    browser: GoogleMeetPlatformBrowser = field(default_factory=GoogleMeetPlatformBrowser)
    dial_in: GoogleMeetPlatformDialIn = field(default_factory=GoogleMeetPlatformDialIn)


GOOGLE_MEET_PLATFORM_ADAPTER = GoogleMeetPlatformAdapter()
