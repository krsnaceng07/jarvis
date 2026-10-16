"""Zoom Web Client browser automation adapter and DOM inspection routines."""

from __future__ import annotations

import logging
from typing import Any

from ..config import ZoomMeetingsConfig
from .types import (
    ZoomManualActionReason,
    ZoomPlatformState,
    ZoomTranscriptEntry,
)

logger = logging.getLogger(__name__)

# Essential Zoom origins for media and device permissions
ZOOM_PERMISSION_ORIGINS = [
    "https://app.zoom.us",
    "https://zoom.us",
    "https://*.zoom.us",
    "https://app.zoomgov.com",
    "https://zoomgov.com",
]

# DOM Selectors for Zoom Web Client
SELECTORS = {
    "interstitial_join_from_browser": [
        'a[href*="/wc/join/"]',
        'a[href*="/wc/"]',
        "a.join-from-browser",
        "a#join-from-browser",
    ],
    "guest_name_input": [
        "input#input-for-name",
        'input[name="inputname"]',
        "input.zm-input__inner",
        'input[placeholder*="name" i]',
        'input[aria-label*="name" i]',
    ],
    "passcode_input": [
        "input#input-for-pwd",
        'input[name="inputpasscode"]',
        'input[type="password"]',
        'input[placeholder*="passcode" i]',
    ],
    "join_button": [
        "button#joinBtn",
        "button.preview-join-button",
        'button[aria-label*="Join" i]',
        "button.zm-btn--primary",
    ],
    "camera_toggle": [
        "#btnJoinVideo",
        'button[aria-label*="camera" i]',
        'button[aria-label*="video" i]',
        'button[aria-label*="Stop Video" i]',
        'button[aria-label*="Turn off video" i]',
    ],
    "mic_toggle": [
        "#btnJoinAudio",
        'button[aria-label*="microphone" i]',
        'button[aria-label*="audio" i]',
        'button[aria-label*="Mute" i]',
        'button[aria-label*="Unmute" i]',
    ],
    "in_call_indicator": [
        "#foot-bar",
        "#wc-footer",
        ".meeting-app",
        'button[aria-label*="Leave" i]',
        'button[aria-label*="End" i]',
        ".footer__btns-container",
    ],
    "leave_button": [
        'button[aria-label*="Leave" i]',
        'button[aria-label*="Leave Meeting" i]',
        "button.footer-menu__leave-btn",
        "button#btnLeave",
    ],
    "leave_confirm_button": [
        "button.leave-meeting-options__btn",
        'button[aria-label*="Leave Meeting" i]',
        "button.zm-btn--danger",
    ],
    "captions_container": [
        ".closed-caption-content",
        ".transcription-item",
        ".transcript-bubble",
        ".transcription-text",
        ".closed-caption-item",
    ],
    "waiting_room_indicator": [
        "#waiting-room-container",
        ".waiting-room",
        ".wait-box",
    ],
}

# Text patterns for manual action & policy detection
MANUAL_ACTION_PATTERNS: list[tuple[list[str], ZoomManualActionReason, str]] = [
    (
        [
            "the host has disabled joining from the browser",
            "join from browser is disabled",
            "join from browser has been disabled",
            "please install the zoom client",
        ],
        ZoomManualActionReason.BROWSER_JOIN_DISABLED,
        "Browser join is disabled by the meeting host or organization policy. Join using native Zoom client.",
    ),
    (
        [
            "sign in to join",
            "please sign in",
            "only authenticated users can join",
            "sign in with google",
            "sign in with sso",
        ],
        ZoomManualActionReason.AUTHENTICATION_REQUIRED,
        "Meeting requires authentication. Please sign into Zoom in this browser profile.",
    ),
    (
        [
            "enter your email to continue",
            "email verification",
            "we sent a verification code to",
            "verify your email",
        ],
        ZoomManualActionReason.EMAIL_VERIFICATION_REQUIRED,
        "Email verification required. Please verify your email in this browser profile.",
    ),
    (
        [
            "please enter the meeting passcode",
            "incorrect passcode",
            "the passcode was incorrect",
            "invalid passcode",
        ],
        ZoomManualActionReason.PASSCODE_REQUIRED,
        "Valid meeting passcode required.",
    ),
    (
        [
            "please solve the challenge",
            "security check",
            "recaptcha",
            "arkose",
            "complete the puzzle",
        ],
        ZoomManualActionReason.CAPTCHA_REQUIRED,
        "CAPTCHA / security verification challenge detected. Please complete it in the browser.",
    ),
    (
        [
            "please wait, the meeting host will let you in soon",
            "waiting for the host to start this meeting",
            "waiting room",
            "the host will admit you soon",
        ],
        ZoomManualActionReason.WAITING_ROOM_HOST_ADMISSION,
        "Participant is currently in the Zoom Waiting Room awaiting host admission.",
    ),
    (
        [
            "allow zoom to use your microphone",
            "allow zoom to access your camera",
            "permission requested",
            "browser permissions",
        ],
        ZoomManualActionReason.DEVICE_PERMISSIONS_REQUIRED,
        "Browser device permission required.",
    ),
    (
        [
            "this meeting has been ended by host",
            "the host has ended this meeting",
            "you have been removed from the meeting",
            "meeting ended",
        ],
        ZoomManualActionReason.HOST_ENDED_MEETING,
        "The meeting was ended by the host or the participant was removed.",
    ),
]


class ZoomPlatformAdapter:
    """Platform automation adapter for Zoom Web Client."""

    def __init__(self, config: ZoomMeetingsConfig) -> None:
        self.config = config

    def grant_permissions_script(self) -> str:
        """Return JavaScript snippet or CDP permission list to pre-grant media devices."""
        return """
        // Pre-grant audio & media queries for app.zoom.us
        if (navigator.permissions && navigator.permissions.query) {
            navigator.permissions.query({ name: 'microphone' }).catch(() => {});
        }
        """

    def analyze_dom_text(
        self, page_text: str
    ) -> tuple[bool, ZoomManualActionReason | None, str | None]:
        """Inspect page text for policy blocks, auth gates, waiting room, or manual actions."""
        if not page_text:
            return False, None, None

        normalized = page_text.lower()
        for needles, reason, msg in MANUAL_ACTION_PATTERNS:
            if any(needle in normalized for needle in needles):
                return True, reason, msg

        return False, None, None

    def evaluate_in_call_state(
        self,
        has_in_call_dom: bool,
        page_text: str,
    ) -> ZoomPlatformState:
        """Determine current Zoom platform lifecycle state."""
        is_manual, reason, _ = self.analyze_dom_text(page_text)
        if is_manual:
            if reason == ZoomManualActionReason.WAITING_ROOM_HOST_ADMISSION:
                return ZoomPlatformState.WAITING_ROOM
            if reason == ZoomManualActionReason.HOST_ENDED_MEETING:
                return ZoomPlatformState.ENDED
            return ZoomPlatformState.PRE_JOIN

        if has_in_call_dom:
            return ZoomPlatformState.IN_CALL

        return ZoomPlatformState.PRE_JOIN

    def parse_captions(self, raw_elements: list[dict[str, Any]]) -> list[ZoomTranscriptEntry]:
        """Convert raw caption DOM element payloads into structured transcript entries."""
        entries: list[ZoomTranscriptEntry] = []
        for elem in raw_elements:
            text = str(elem.get("text") or "").strip()
            speaker = str(elem.get("speaker") or "Speaker").strip()
            if text:
                entries.append(
                    ZoomTranscriptEntry(
                        speaker=speaker,
                        text=text,
                        timestamp=float(elem.get("timestamp", 0) or 0),
                        is_final=bool(elem.get("is_final", True)),
                    )
                )
        return entries
