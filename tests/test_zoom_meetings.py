"""Tests for src/plugins/zoom_meetings.py.

Mirrors tests of extensions/zoom-meetings/src/transports/zoom-meetings-urls.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.zoom_meetings import (
    ZOOM_MEETINGS_TOOL_ACTIONS,
    is_valid_zoom_meeting_url,
    resolve_zoom_meetings_config,
)


def test_zoom_meetings_tool_actions():
    assert "join" in ZOOM_MEETINGS_TOOL_ACTIONS
    assert "leave" in ZOOM_MEETINGS_TOOL_ACTIONS
    assert "status" in ZOOM_MEETINGS_TOOL_ACTIONS
    assert "transcript" in ZOOM_MEETINGS_TOOL_ACTIONS
    assert "speak" in ZOOM_MEETINGS_TOOL_ACTIONS
    assert len(ZOOM_MEETINGS_TOOL_ACTIONS) == 5


def test_is_valid_zoom_meeting_url():
    standard_url = "https://zoom.us/j/1234567890"
    subdomain_url = "https://example.zoom.us/j/12345678901"
    web_client_url = "https://app.zoom.us/wc/1234567890/join"
    invalid_url = "https://zoom.us/invalid/path"

    assert is_valid_zoom_meeting_url(standard_url) is True
    assert is_valid_zoom_meeting_url(subdomain_url) is True
    assert is_valid_zoom_meeting_url(web_client_url) is True
    assert is_valid_zoom_meeting_url(invalid_url) is False


def test_resolve_zoom_meetings_config_defaults():
    cfg = resolve_zoom_meetings_config(None)
    assert cfg.enabled is True
    assert cfg.defaultMode == "agent"
    assert cfg.chrome.guestName == "OpenClaw Agent"
    assert cfg.chrome_node_id is None
