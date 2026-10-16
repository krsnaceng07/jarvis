"""Tests for src/plugins/meeting_runtime.py.

Mirrors tests of meeting-runtime.ts in OpenClaw.
"""

from __future__ import annotations


from src.plugins.meeting_runtime import (
    MEETING_NODE_COMMANDS,
    MeetingSessionState,
    resolve_meeting_node_command,
)


def test_meeting_node_commands():
    assert MEETING_NODE_COMMANDS["google-meet"] == "googlemeet.chrome"
    assert MEETING_NODE_COMMANDS["teams-meetings"] == "teamsmeetings.chrome"
    assert MEETING_NODE_COMMANDS["zoom-meetings"] == "zoommeetings.chrome"


def test_resolve_meeting_node_command():
    assert resolve_meeting_node_command("google-meet") == "googlemeet.chrome"
    assert resolve_meeting_node_command("teams-meetings") == "teamsmeetings.chrome"
    assert resolve_meeting_node_command("zoom-meetings") == "zoommeetings.chrome"
    assert resolve_meeting_node_command("unknown-plugin") is None


def test_meeting_session_state_defaults():
    state = MeetingSessionState(
        session_id="sess_123",
        plugin_id="google-meet",
        meeting_url="https://meet.google.com/abc-defg-hij",
    )
    assert state.mode == "agent"
    assert state.in_call is False
    assert state.speech_output_verified is False
    assert state.manual_action_required is None
