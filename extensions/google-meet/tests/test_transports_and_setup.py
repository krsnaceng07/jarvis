"""Tests for Google Meet Chrome transports, Twilio DTMF plans, manual actions, and setup diagnostics."""

import pytest

from extensions.google_meet.src.browser_manual_action_error import (
    GoogleMeetBrowserManualActionError,
    is_google_meet_browser_manual_action_error,
)
from extensions.google_meet.src.config import resolve_google_meet_config
from extensions.google_meet.src.setup import get_google_meet_setup_status
from extensions.google_meet.src.transports.google_meet_platform_adapter import (
    GOOGLE_MEET_PLATFORM_ADAPTER,
)
from extensions.google_meet.src.transports.twilio import (
    build_meet_dtmf_sequence,
    normalize_dial_in_number,
    prefix_dtmf_wait,
)
from extensions.google_meet.src.transports.types import GoogleMeetChromeHealth


def test_twilio_phone_and_dtmf_normalization():
    assert normalize_dial_in_number("+1 (555) 123-4567") == "+15551234567"
    assert normalize_dial_in_number("5551234567") == "5551234567"

    with pytest.raises(ValueError, match="must be a phone number"):
        normalize_dial_in_number("not-a-number")

    # PIN without # appends #
    assert build_meet_dtmf_sequence(pin="123456") == "123456#"
    # PIN with # preserves #
    assert build_meet_dtmf_sequence(pin="123456#") == "123456#"

    # Custom DTMF sequence with pauses
    assert build_meet_dtmf_sequence(dtmf_sequence="ww123456#") == "ww123456#"

    # Prefix wait calculation (500ms per 'w')
    assert prefix_dtmf_wait("123456#", delay_ms=1000) == "ww123456#"
    assert prefix_dtmf_wait("123456#", delay_ms=1500) == "www123456#"
    assert prefix_dtmf_wait("123456#", delay_ms=0) == "123456#"


def test_browser_manual_action_error():
    err = GoogleMeetBrowserManualActionError(
        {
            "manualAction": {
                "reason": "meet-admission-required",
                "message": "Admit the browser participant in Google Meet, then retry.",
            },
            "browserUrl": "https://meet.google.com/abc-defg-hij",
        }
    )
    assert is_google_meet_browser_manual_action_error(err)
    assert "meet-admission-required" in str(err)
    assert err.payload["browserUrl"] == "https://meet.google.com/abc-defg-hij"


def test_setup_diagnostics_chrome_and_twilio():
    cfg_res = resolve_google_meet_config(
        {
            "defaultTransport": "chrome-node",
            "chromeNode": {"node": "parallels-macos"},
            "chrome": {
                "guestName": "JARVIS Agent",
                "autoJoin": True,
                "reuseExistingTab": True,
            },
            "twilio": {
                "defaultDialInNumber": "+15551234567",
                "defaultPin": "987654",
            },
        }
    )
    cfg = cfg_res.unwrap()
    status = get_google_meet_setup_status(cfg)
    check_ids = [c.id for c in status.checks]

    assert "guest-join-defaults" in check_ids
    assert "chrome-node-target" in check_ids
    assert "audio-bridge" in check_ids

    # Pinned node check passes
    node_check = next(c for c in status.checks if c.id == "chrome-node-target")
    assert node_check.ok is True
    assert "parallels-macos" in node_check.message


def test_platform_adapter_classification():
    health = GoogleMeetChromeHealth(
        in_call=False,
        browser_url="https://accounts.google.com/signin",
        manual_action=None,
    )
    classified = GOOGLE_MEET_PLATFORM_ADAPTER.browser.classify_manual_action(health)
    assert classified is None or hasattr(classified, "reason")
