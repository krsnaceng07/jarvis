"""Unit tests for Zoom Meetings URL parsing, validation, and web app conversion."""

from __future__ import annotations

import pytest

from extensions.zoom_meetings.src.zoom_url import (
    extract_meeting_id,
    extract_passcode,
    is_valid_zoom_host,
    is_zoom_url,
    normalize_zoom_url,
    to_zoom_web_app_url,
)


def test_zoom_host_validation() -> None:
    assert is_valid_zoom_host("zoom.us") is True
    assert is_valid_zoom_host("us02web.zoom.us") is True
    assert is_valid_zoom_host("example.zoom.us") is True
    assert is_valid_zoom_host("app.zoomgov.com") is True
    assert is_valid_zoom_host("zoomgov.com") is True

    assert is_valid_zoom_host("evilzoom.us.attacker.com") is False
    assert is_valid_zoom_host("google.com") is False
    assert is_valid_zoom_host(None) is False


def test_extract_meeting_id_and_passcode() -> None:
    assert extract_meeting_id("/j/12345678901") == "12345678901"
    assert extract_meeting_id("/wc/join/987654321") == "987654321"
    assert extract_meeting_id("/my/jarvisbot") == "jarvisbot"

    assert extract_passcode("https://zoom.us/j/123?pwd=secretPasscode123") == "secretPasscode123"
    assert extract_passcode("pwd=secretPasscode123&uname=guest") == "secretPasscode123"
    assert extract_passcode("https://zoom.us/j/123") is None


def test_normalize_zoom_url() -> None:
    # Standard join link
    norm1 = normalize_zoom_url("https://zoom.us/j/12345678901")
    assert norm1 == "https://zoom.us/j/12345678901"

    # Subdomain join link with passcode
    norm2 = normalize_zoom_url("example.zoom.us/j/12345678901?pwd=abc")
    assert norm2 == "https://example.zoom.us/j/12345678901?pwd=abc"

    # Gov cloud
    norm3 = normalize_zoom_url("https://zoomgov.com/j/999888777")
    assert norm3 == "https://zoomgov.com/j/999888777"

    # Invalid host or path
    with pytest.raises(ValueError, match="Unsupported Zoom meeting host"):
        normalize_zoom_url("https://unsupported.com/j/123")

    with pytest.raises(ValueError, match="Invalid Zoom meeting URL path"):
        normalize_zoom_url("https://zoom.us/about")


def test_to_zoom_web_app_url() -> None:
    # 1. Standard join to app.zoom.us/wc/join/<id>
    web1 = to_zoom_web_app_url("https://zoom.us/j/12345678901")
    assert web1 == "https://app.zoom.us/wc/join/12345678901"

    # 2. With passcode and guest name
    web2 = to_zoom_web_app_url(
        "https://zoom.us/j/12345678901?pwd=secret", guest_name="JARVIS Agent"
    )
    assert "https://app.zoom.us/wc/join/12345678901?" in web2
    assert "pwd=secret" in web2
    assert "uname=JARVIS+Agent" in web2

    # 3. Account subdomain preservation
    web3 = to_zoom_web_app_url("https://acme.zoom.us/j/987654321")
    assert web3 == "https://acme.zoom.us/wc/join/987654321"


def test_is_zoom_url() -> None:
    assert is_zoom_url("https://zoom.us/j/123456789") is True
    assert is_zoom_url("example.zoom.us/j/123456789") is True
    assert is_zoom_url("https://teams.microsoft.com/l/meetup-join/123") is False
    assert is_zoom_url("") is False
    assert is_zoom_url(None) is False
