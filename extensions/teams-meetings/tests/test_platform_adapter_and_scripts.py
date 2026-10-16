"""Tests for Teams Meetings platform adapter, DOM scripts, and manual action parsing."""

from __future__ import annotations

import json

from extensions.teams_meetings.src.transports.teams_page_scripts import (
    teams_leave_script,
    teams_status_script,
    teams_transcript_script,
)
from extensions.teams_meetings.src.transports.teams_platform_adapter import (
    TEAMS_MEETINGS_PLATFORM_ADAPTER,
    classify_manual_action_reason,
    is_talk_back_mode,
)


def test_is_talk_back_mode() -> None:
    assert is_talk_back_mode("agent") is True
    assert is_talk_back_mode("bidi") is True
    assert is_talk_back_mode("transcribe") is False


def test_classify_manual_action_reason() -> None:
    assert classify_manual_action_reason("teams-login-required") == "login-required"
    assert classify_manual_action_reason("teams-verification-required") == "verification-required"
    assert classify_manual_action_reason("teams-admission-required") == "admission-required"
    assert classify_manual_action_reason("teams-permission-required") == "permission-required"
    assert (
        classify_manual_action_reason("browser-control-unavailable")
        == "browser-control-unavailable"
    )
    assert classify_manual_action_reason("unknown-reason") == "custom"


def test_parse_teams_browser_status_in_call() -> None:
    raw_status = json.dumps(
        {
            "inCall": True,
            "micMuted": False,
            "cameraOff": True,
            "lobbyWaiting": False,
            "captioning": True,
            "transcriptLines": 12,
            "lastCaptionSpeaker": "Alice",
            "lastCaptionText": "Can everyone hear me?",
            "audioInputRouted": True,
            "audioInputDeviceLabel": "BlackHole 2ch (Virtual)",
            "audioOutputRouted": True,
            "audioOutputDeviceLabel": "BlackHole 2ch (Virtual)",
            "url": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0",
            "title": "Microsoft Teams meeting",
            "notes": ["Entered guest name: JARVIS", "Clicked Join now button."],
        }
    )
    health = TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.parse_status({"result": raw_status})
    assert health is not None
    assert health.in_call is True
    assert health.mic_muted is False
    assert health.captioning is True
    assert health.transcript_lines == 12
    assert health.last_caption_speaker == "Alice"
    assert health.last_caption_text == "Can everyone hear me?"
    assert health.audio_input_routed is True
    assert health.manual_action is None


def test_parse_teams_browser_status_manual_actions() -> None:
    # 1. Login required
    login_raw = json.dumps(
        {
            "inCall": False,
            "manualAction": {
                "reason": "teams-login-required",
                "message": "Sign in to Microsoft Teams in the JARVIS browser profile, then retry.",
            },
        }
    )
    h_login = TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.parse_status({"result": login_raw})
    assert h_login is not None
    assert h_login.in_call is False
    assert h_login.manual_action is not None
    assert h_login.manual_action.reason == "teams-login-required"
    assert h_login.manual_action.category == "login-required"

    # 2. Admission required (lobby)
    lobby_raw = json.dumps(
        {
            "inCall": False,
            "lobbyWaiting": True,
            "manualAction": {
                "reason": "teams-admission-required",
                "message": "Admit the JARVIS browser participant in Microsoft Teams, then retry speech.",
            },
        }
    )
    h_lobby = TEAMS_MEETINGS_PLATFORM_ADAPTER.browser.parse_status({"result": lobby_raw})
    assert h_lobby is not None
    assert h_lobby.lobby_waiting is True
    assert h_lobby.manual_action is not None
    assert h_lobby.manual_action.reason == "teams-admission-required"


def test_scripts_generation() -> None:
    status_script = teams_status_script(
        allow_microphone=True,
        auto_join=True,
        guest_name="JARVIS",
        caption_session_id="session_123",
        capture_captions=True,
        read_only=False,
    )
    assert "BlackHole" in status_script
    assert "prejoin-join-button" in status_script
    assert "JARVIS" in status_script

    transcript_script = teams_transcript_script(
        meeting_url="https://teams.microsoft.com/l/meetup-join/19%3ameeting_123%40thread.v2/0",
        meeting_session_id="session_123",
        finalize=True,
    )
    assert "__openclawTeamsCaptions" in transcript_script

    leave_script = teams_leave_script(
        meeting_url="https://teams.microsoft.com/l/meetup-join/19%3ameeting_123%40thread.v2/0"
    )
    assert "hangup-button" in leave_script
