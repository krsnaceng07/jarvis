"""Tests for src/plugins/google_meet.py.

Mirrors tests of extensions/google-meet/src/config.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.google_meet import (
    GOOGLE_MEET_TOOL_ACTIONS,
    is_valid_meet_url,
    resolve_google_meet_config,
)


def test_google_meet_tool_actions():
    assert "join" in GOOGLE_MEET_TOOL_ACTIONS
    assert "create" in GOOGLE_MEET_TOOL_ACTIONS
    assert "test_speech" in GOOGLE_MEET_TOOL_ACTIONS
    assert len(GOOGLE_MEET_TOOL_ACTIONS) == 18


def test_is_valid_meet_url():
    assert is_valid_meet_url("https://meet.google.com/abc-defg-hij") is True
    assert is_valid_meet_url("https://meet.google.com/ABC-DEFG-HIJ") is True
    assert is_valid_meet_url("https://google.com") is False
    assert is_valid_meet_url("http://meet.google.com/abc-defg-hij") is False


def test_resolve_google_meet_config_defaults():
    cfg = resolve_google_meet_config(None)
    assert cfg.enabled is True
    assert cfg.defaultTransport == "chrome"
    assert cfg.defaultMode == "agent"
    assert cfg.chrome.guestName == "OpenClaw Agent"
    assert cfg.chrome.autoJoin is True
    assert cfg.chrome_node_id is None


def test_resolve_google_meet_config_custom():
    custom = {
        "enabled": True,
        "defaultTransport": "chrome-node",
        "defaultMode": "realtime",  # Legacy alias -> agent
        "chromeNode": {"node": "parallels-mac"},
        "chrome": {"guestName": "Jarvis Bot", "autoJoin": False},
    }
    cfg = resolve_google_meet_config(custom)
    assert cfg.defaultTransport == "chrome-node"
    assert cfg.defaultMode == "agent"
    assert cfg.chrome_node_id == "parallels-mac"
    assert cfg.chrome.guestName == "Jarvis Bot"
    assert cfg.chrome.autoJoin is False
