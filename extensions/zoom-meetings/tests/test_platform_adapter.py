"""Unit tests for Zoom platform adapter, DOM text analysis, and manual action detection."""

from __future__ import annotations

from extensions.zoom_meetings.src.config import ZoomMeetingsConfig
from extensions.zoom_meetings.src.transports.types import (
    ZoomManualActionReason,
    ZoomPlatformState,
)
from extensions.zoom_meetings.src.transports.zoom_platform_adapter import ZoomPlatformAdapter


def test_manual_action_detection_matrix() -> None:
    adapter = ZoomPlatformAdapter(ZoomMeetingsConfig())

    # 1. Browser join disabled
    is_m, reason, _ = adapter.analyze_dom_text("The host has disabled joining from the browser.")
    assert is_m is True
    assert reason == ZoomManualActionReason.BROWSER_JOIN_DISABLED

    # 2. Authentication required
    is_m, reason, _ = adapter.analyze_dom_text(
        "Only authenticated users can join this meeting. Sign In to Join."
    )
    assert is_m is True
    assert reason == ZoomManualActionReason.AUTHENTICATION_REQUIRED

    # 3. Email verification
    is_m, reason, _ = adapter.analyze_dom_text(
        "Please enter your email to continue. We sent a verification code."
    )
    assert is_m is True
    assert reason == ZoomManualActionReason.EMAIL_VERIFICATION_REQUIRED

    # 4. Passcode required
    is_m, reason, _ = adapter.analyze_dom_text("Please enter the meeting passcode to enter.")
    assert is_m is True
    assert reason == ZoomManualActionReason.PASSCODE_REQUIRED

    # 5. Security / CAPTCHA challenge
    is_m, reason, _ = adapter.analyze_dom_text(
        "Security Check: Please solve the challenge / reCAPTCHA."
    )
    assert is_m is True
    assert reason == ZoomManualActionReason.CAPTCHA_REQUIRED

    # 6. Waiting room
    is_m, reason, _ = adapter.analyze_dom_text(
        "Please wait, the meeting host will let you in soon. Waiting Room."
    )
    assert is_m is True
    assert reason == ZoomManualActionReason.WAITING_ROOM_HOST_ADMISSION

    # 7. Device permissions
    is_m, reason, _ = adapter.analyze_dom_text("Allow Zoom to use your microphone and camera.")
    assert is_m is True
    assert reason == ZoomManualActionReason.DEVICE_PERMISSIONS_REQUIRED

    # 8. Host ended meeting
    is_m, reason, _ = adapter.analyze_dom_text("This meeting has been ended by host.")
    assert is_m is True
    assert reason == ZoomManualActionReason.HOST_ENDED_MEETING

    # 9. Normal in-call text without policy blockers
    is_m, reason, _ = adapter.analyze_dom_text("Welcome to the weekly sync. Participants: 4.")
    assert is_m is False
    assert reason is None


def test_evaluate_in_call_state() -> None:
    adapter = ZoomPlatformAdapter(ZoomMeetingsConfig())

    # In call with active DOM controls
    state_in_call = adapter.evaluate_in_call_state(has_in_call_dom=True, page_text="Meeting active")
    assert state_in_call == ZoomPlatformState.IN_CALL

    # In waiting room
    state_waiting = adapter.evaluate_in_call_state(
        has_in_call_dom=False,
        page_text="Please wait, the meeting host will let you in soon.",
    )
    assert state_waiting == ZoomPlatformState.WAITING_ROOM

    # Meeting ended
    state_ended = adapter.evaluate_in_call_state(
        has_in_call_dom=False,
        page_text="This meeting has been ended by host.",
    )
    assert state_ended == ZoomPlatformState.ENDED


def test_parse_captions() -> None:
    adapter = ZoomPlatformAdapter(ZoomMeetingsConfig())
    raw_payloads = [
        {"speaker": "Alice", "text": "Can everyone hear me?", "timestamp": 1700000001.0},
        {"speaker": "Bob", "text": "Yes, loud and clear.", "timestamp": 1700000004.0},
    ]

    entries = adapter.parse_captions(raw_payloads)
    assert len(entries) == 2
    assert entries[0].speaker == "Alice"
    assert entries[0].text == "Can everyone hear me?"
    assert entries[1].speaker == "Bob"
    assert entries[1].text == "Yes, loud and clear."
