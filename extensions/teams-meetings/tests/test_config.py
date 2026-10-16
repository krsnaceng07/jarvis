"""Tests for Teams Meetings configuration schema and resolution."""

from __future__ import annotations

from extensions.teams_meetings.src.config import resolve_teams_meetings_config
from extensions.teams_meetings.src.config_compat import migrate_legacy_teams_meetings_config


def test_default_config_resolution() -> None:
    res = resolve_teams_meetings_config({})
    assert res.is_ok is True
    cfg = res.unwrap()
    assert cfg.enabled is True
    assert cfg.default_transport == "chrome"
    assert cfg.default_mode == "agent"
    assert cfg.chrome.auto_join is True
    assert cfg.chrome.guest_name == "JARVIS"
    assert cfg.chrome.reuse_existing_tab is True
    assert cfg.chrome.audio_backend == "auto"


def test_custom_config_resolution() -> None:
    raw = {
        "enabled": True,
        "defaultTransport": "chrome-node",
        "defaultMode": "bidi",
        "chrome": {
            "guestName": "TeamsBot",
            "autoJoin": False,
            "reuseExistingTab": False,
            "audioBackend": "blackhole-2ch",
            "joinTimeoutMs": 45000,
            "waitForInCallMs": 10000,
        },
        "chromeNode": {
            "node": "parallels-macos",
        },
        "realtime": {
            "agentId": "consultant",
            "introMessage": "Custom intro.",
        },
        "defaults": {
            "meeting": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0",
        },
    }
    res = resolve_teams_meetings_config(raw)
    assert res.is_ok is True
    cfg = res.unwrap()
    assert cfg.default_transport == "chrome-node"
    assert cfg.default_mode == "bidi"
    assert cfg.chrome.guest_name == "TeamsBot"
    assert cfg.chrome.auto_join is False
    assert cfg.chrome.reuse_existing_tab is False
    assert cfg.chrome.audio_backend == "blackhole-2ch"
    assert cfg.chrome.join_timeout_ms == 45000
    assert cfg.chrome.wait_for_in_call_ms == 10000
    assert cfg.chrome_node.node == "parallels-macos"
    assert cfg.realtime.agent_id == "consultant"
    assert cfg.realtime.intro_message == "Custom intro."
    assert (
        cfg.defaults.meeting
        == "https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0"
    )


def test_legacy_config_migration() -> None:
    legacy = {
        "guest_name": "OldGuest",
        "auto_join": True,
        "node": "legacy-node",
    }
    migrated, changed = migrate_legacy_teams_meetings_config(legacy)
    assert changed is True
    assert migrated["chrome"]["guestName"] == "OldGuest"
    assert migrated["chrome"]["autoJoin"] is True
    assert migrated["chromeNode"]["node"] == "legacy-node"
