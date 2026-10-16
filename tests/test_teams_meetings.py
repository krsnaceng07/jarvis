"""Tests for src/plugins/teams_meetings.py.

Mirrors tests of extensions/teams-meetings/src/transports/teams-meetings-urls.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.teams_meetings import (
    TEAMS_MEETINGS_TOOL_ACTIONS,
    is_valid_teams_meeting_url,
    resolve_teams_meetings_config,
)


def test_teams_meetings_tool_actions():
    assert "join" in TEAMS_MEETINGS_TOOL_ACTIONS
    assert "leave" in TEAMS_MEETINGS_TOOL_ACTIONS
    assert "status" in TEAMS_MEETINGS_TOOL_ACTIONS
    assert "transcript" in TEAMS_MEETINGS_TOOL_ACTIONS
    assert "speak" in TEAMS_MEETINGS_TOOL_ACTIONS
    assert len(TEAMS_MEETINGS_TOOL_ACTIONS) == 5


def test_is_valid_teams_meeting_url():
    work_url = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_1234567890%40thread.v2/0"
    consumer_url = "https://teams.live.com/meet/9876543210"
    invalid_url = "https://teams.microsoft.com/invalid/path"

    assert is_valid_teams_meeting_url(work_url) is True
    assert is_valid_teams_meeting_url(consumer_url) is True
    assert is_valid_teams_meeting_url(invalid_url) is False


def test_resolve_teams_meetings_config_defaults():
    cfg = resolve_teams_meetings_config(None)
    assert cfg.enabled is True
    assert cfg.defaultMode == "agent"
    assert cfg.chrome.guestName == "OpenClaw Agent"
    assert cfg.chrome_node_id is None
