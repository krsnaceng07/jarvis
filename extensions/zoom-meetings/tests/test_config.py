"""Unit tests for Zoom Meetings configuration parsing and resolution."""

from __future__ import annotations

from extensions.zoom_meetings.src.config import resolve_zoom_meetings_config


def test_default_config_resolution() -> None:
    res = resolve_zoom_meetings_config({})
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.enabled is True
    assert cfg.default_transport == "chrome"
    assert cfg.default_mode == "agent"
    assert cfg.chrome.guest_name == "JARVIS"
    assert cfg.chrome.auto_join is True
    assert cfg.chrome.grant_media_permissions is True


def test_custom_config_resolution() -> None:
    raw = {
        "enabled": True,
        "defaultTransport": "chrome-node",
        "defaultMode": "bidi",
        "chrome": {
            "guestName": "Custom Agent",
            "audioBackend": "pipewire-pulse",
            "joinTimeoutMs": 45000,
            "passcode": "roomPass123",
        },
        "chromeNode": {"node": "remote-node-1"},
        "realtime": {"introMessage": "Custom intro"},
        "defaults": {"meeting": "https://zoom.us/j/123456789"},
    }

    res = resolve_zoom_meetings_config(raw)
    assert res.is_ok
    cfg = res.unwrap()
    assert cfg.default_transport == "chrome-node"
    assert cfg.default_mode == "bidi"
    assert cfg.chrome.guest_name == "Custom Agent"
    assert cfg.chrome.audio_backend == "pipewire-pulse"
    assert cfg.chrome.join_timeout_ms == 45000
    assert cfg.chrome.passcode == "roomPass123"
    assert cfg.chrome_node.node == "remote-node-1"
    assert cfg.realtime.intro_message == "Custom intro"
    assert cfg.defaults.meeting == "https://zoom.us/j/123456789"


def test_invalid_config_validation() -> None:
    res_bad_trans = resolve_zoom_meetings_config({"defaultTransport": "invalid_trans"})
    assert res_bad_trans.is_ok is False
    assert "Invalid defaultTransport" in str(res_bad_trans.error)

    res_bad_mode = resolve_zoom_meetings_config({"defaultMode": "invalid_mode"})
    assert res_bad_mode.is_ok is False
    assert "Invalid defaultMode" in str(res_bad_mode.error)
