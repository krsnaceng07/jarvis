"""Teams Meetings platform adapter: URL, DOM parsing, and manual-action taxonomy."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ..teams_url import normalize_teams_url
from .teams_page_scripts import (
    teams_leave_script,
    teams_status_script,
    teams_transcript_script,
)
from .teams_platform_constants import TEAMS_MEETINGS_NODE_COMMAND
from .teams_urls import (
    is_recoverable_teams_tab,
    is_same_teams_url_for_reuse,
    normalize_teams_url_for_reuse,
)
from .types import (
    TeamsMeetingsBrowserCandidateTab,
    TeamsMeetingsChromeHealth,
    TeamsMeetingsManualAction,
    TeamsMeetingsTranscriptLine,
    TeamsMeetingsTranscriptSnapshot,
)

TEAMS_MANUAL_ACTION_CATEGORIES: dict[str, str] = {
    "browser-control-unavailable": "browser-control-unavailable",
    "teams-login-required": "login-required",
    "teams-verification-required": "verification-required",
    "teams-admission-required": "admission-required",
    "teams-audio-choice-required": "audio-choice-required",
    "teams-locale-required": "locale-required",
    "teams-permission-required": "permission-required",
    "teams-session-conflict": "session-conflict",
}


def classify_manual_action_reason(reason: str) -> str:
    return TEAMS_MANUAL_ACTION_CATEGORIES.get(reason, "custom")


def is_talk_back_mode(mode: str) -> bool:
    return mode in ("agent", "bidi")


def browser_result_string(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    val = result.get("result")
    if isinstance(val, str) and val.strip():
        return val
    return None


def parse_teams_browser_status(result: Any) -> TeamsMeetingsChromeHealth | None:
    raw = browser_result_string(result)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception as err:
        raise ValueError("Teams Meetings browser status JSON is malformed.") from err

    if not isinstance(parsed, dict):
        raise ValueError("Teams Meetings browser status JSON is malformed.")

    manual_action: TeamsMeetingsManualAction | None = None
    if isinstance(parsed.get("manualAction"), dict):
        ma_raw = parsed["manualAction"]
        reason = str(ma_raw.get("reason", ""))
        message = str(ma_raw.get("message", ""))
        manual_action = TeamsMeetingsManualAction(
            reason=reason,
            message=message,
            category=classify_manual_action_reason(reason),
        )

    recent_transcript: list[TeamsMeetingsTranscriptLine] = []
    if isinstance(parsed.get("recentTranscript"), list):
        for item in parsed["recentTranscript"]:
            if isinstance(item, dict) and item.get("text"):
                text = str(item["text"]).strip()
                if text:
                    recent_transcript.append(
                        TeamsMeetingsTranscriptLine(
                            text=text,
                            speaker=str(item.get("speaker"))
                            if item.get("speaker") is not None
                            else None,
                            at=str(item.get("at")) if item.get("at") is not None else None,
                        )
                    )

    notes = [str(n) for n in parsed.get("notes", []) if isinstance(n, str)]

    return TeamsMeetingsChromeHealth(
        in_call=parsed.get("inCall") is True,
        inCall=parsed.get("inCall") is True,
        mic_muted=parsed.get("micMuted"),
        micMuted=parsed.get("micMuted"),
        camera_off=parsed.get("cameraOff"),
        cameraOff=parsed.get("cameraOff"),
        lobby_waiting=parsed.get("lobbyWaiting"),
        lobbyWaiting=parsed.get("lobbyWaiting"),
        captioning=parsed.get("captioning"),
        captions_enabled_attempted=parsed.get("captionsEnabledAttempted"),
        captionsEnabledAttempted=parsed.get("captionsEnabledAttempted"),
        transcript_lines=int(parsed.get("transcriptLines", 0)),
        transcriptLines=int(parsed.get("transcriptLines", 0)),
        last_caption_at=parsed.get("lastCaptionAt"),
        lastCaptionAt=parsed.get("lastCaptionAt"),
        last_caption_speaker=parsed.get("lastCaptionSpeaker"),
        lastCaptionSpeaker=parsed.get("lastCaptionSpeaker"),
        last_caption_text=parsed.get("lastCaptionText"),
        lastCaptionText=parsed.get("lastCaptionText"),
        recent_transcript=recent_transcript if recent_transcript else None,
        audio_input_routed=parsed.get("audioInputRouted"),
        audioInputRouted=parsed.get("audioInputRouted"),
        audio_input_device_label=parsed.get("audioInputDeviceLabel"),
        audioInputDeviceLabel=parsed.get("audioInputDeviceLabel"),
        audio_input_route_error=parsed.get("audioInputRouteError"),
        audio_output_routed=parsed.get("audioOutputRouted"),
        audioOutputRouted=parsed.get("audioOutputRouted"),
        audio_output_device_label=parsed.get("audioOutputDeviceLabel"),
        audioOutputDeviceLabel=parsed.get("audioOutputDeviceLabel"),
        audio_output_route_error=parsed.get("audioOutputRouteError"),
        manual_action=manual_action,
        browser_url=parsed.get("url"),
        browserUrl=parsed.get("url"),
        browser_title=parsed.get("title"),
        browserTitle=parsed.get("title"),
        leave_reason=parsed.get("leaveReason"),
        notes=notes,
    )


def parse_teams_leave_result(result: Any) -> dict[str, Any]:
    raw = browser_result_string(result)
    if not raw:
        return {"departed": False}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"departed": False}
    except Exception:
        return {"departed": False}


def parse_teams_transcript(result: Any) -> TeamsMeetingsTranscriptSnapshot:
    raw = browser_result_string(result)
    if not raw:
        return TeamsMeetingsTranscriptSnapshot(dropped_lines=0, lines=[])
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return TeamsMeetingsTranscriptSnapshot(dropped_lines=0, lines=[])
        lines: list[TeamsMeetingsTranscriptLine] = []
        for line in parsed.get("lines", []):
            if isinstance(line, dict) and line.get("text"):
                lines.append(
                    TeamsMeetingsTranscriptLine(
                        speaker=line.get("speaker"),
                        text=line.get("text", ""),
                        at=line.get("at"),
                    )
                )
        return TeamsMeetingsTranscriptSnapshot(
            lines=lines,
            dropped_lines=parsed.get("droppedLines", 0),
            epoch=parsed.get("epoch"),
            url_matched=parsed.get("urlMatched"),
            session_matched=parsed.get("sessionMatched"),
        )
    except Exception:
        return TeamsMeetingsTranscriptSnapshot(dropped_lines=0, lines=[])


@dataclass(frozen=True, slots=True)
class TeamsMeetingsPlatformUrls:
    validate_and_normalize: Callable[[str], str] = normalize_teams_url
    normalize_for_reuse: Callable[[str | None], str | None] = normalize_teams_url_for_reuse
    is_same_meeting: Callable[[str | None, str | None], bool] = is_same_teams_url_for_reuse
    is_recoverable_tab: Callable[[TeamsMeetingsBrowserCandidateTab, str | None], bool] = (
        is_recoverable_teams_tab
    )


@dataclass(frozen=True, slots=True)
class TeamsMeetingsPlatformCaptions:
    def enabled(self, _mode: str) -> bool:
        return True

    def build_transcript_script(
        self, finalize: bool, meeting_session_id: str, meeting_url: str
    ) -> str:
        return teams_transcript_script(meeting_url, meeting_session_id, finalize)

    def parse_transcript(self, result: Any) -> TeamsMeetingsTranscriptSnapshot:
        return parse_teams_transcript(result)


@dataclass(frozen=True, slots=True)
class TeamsMeetingsPlatformBrowser:
    captions: TeamsMeetingsPlatformCaptions = field(default_factory=TeamsMeetingsPlatformCaptions)

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
        **kwargs: Any,
    ) -> str:
        return teams_status_script(
            allow_microphone=self.allows_microphone(mode),
            auto_join=auto_join,
            caption_session_id=meeting_session_id or None,
            capture_captions=capture_captions,
            guest_name=guest_name,
            read_only=read_only,
        )

    def build_leave_script(self, meeting_url: str) -> str:
        return teams_leave_script(meeting_url)

    def permissions(self, allow_microphone: bool, meeting_url: str = "") -> dict[str, Any] | None:
        if allow_microphone:
            return {
                "origin": "https://teams.microsoft.com",
                "permissions": ["audioCapture", "videoCapture"],
                "optionalPermissions": ["speakerSelection"],
            }
        return None

    def parse_status(self, result: Any) -> TeamsMeetingsChromeHealth | None:
        return parse_teams_browser_status(result)

    def parse_leave_result(self, result: Any) -> dict[str, Any]:
        return parse_teams_leave_result(result)


@dataclass(frozen=True, slots=True)
class TeamsMeetingsPlatformAdapter:
    id: str = "teams-meetings"
    display_name: str = "Microsoft Teams"
    browser_label: str = "Teams"
    log_scope: str = "[teams-meetings]"
    node_command_name: str = TEAMS_MEETINGS_NODE_COMMAND
    node_config_path: str = "plugins.entries.teams-meetings.config.chromeNode.node"
    urls: TeamsMeetingsPlatformUrls = field(default_factory=TeamsMeetingsPlatformUrls)
    browser: TeamsMeetingsPlatformBrowser = field(default_factory=TeamsMeetingsPlatformBrowser)


TEAMS_MEETINGS_PLATFORM_ADAPTER = TeamsMeetingsPlatformAdapter()
