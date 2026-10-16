"""Tests for Google Meet plugin registration, tool actions, invoke policy, and agent/bidi modes."""

import pytest

from extensions.google_meet.plugin import entry
from extensions.google_meet.src.node_invoke_policy import GoogleMeetChromeNodeInvokePolicy
from extensions.google_meet.src.plugin_helpers import execute_google_meet_action
from extensions.google_meet.src.plugin_registration import GOOGLE_MEET_GATEWAY_METHOD_SPECS
from extensions.google_meet.src.plugin_schema import GOOGLE_MEET_TOOL_SCHEMA
from extensions.google_meet.src.runtime import GoogleMeetRuntime
from extensions.google_meet.src import runtime_probes
from extensions.google_meet.src.transports.google_meet_platform_adapter import is_talk_back_mode
from extensions.google_meet.src.transports.types import GoogleMeetJoinRequest


def test_plugin_entry_metadata():
    assert entry.id == "google-meet"
    assert entry.kind == "tools"
    assert "Google Meet" in entry.name


def test_node_invoke_policy():
    policy = GoogleMeetChromeNodeInvokePolicy()
    assert policy.is_allowed({"action": "query_tabs"})
    assert policy.is_allowed({"action": "create_room"})
    assert not policy.is_allowed({"action": "unauthorized_action"})


def test_gateway_method_specs_count():
    assert len(GOOGLE_MEET_GATEWAY_METHOD_SPECS) == 16
    methods = [spec["method"] for spec in GOOGLE_MEET_GATEWAY_METHOD_SPECS]
    assert "googlemeet.space.create" in methods
    assert "googlemeet.session.join" in methods
    assert "googlemeet.session.leave" in methods
    assert "googlemeet.attendance.get" in methods
    assert "googlemeet.export.bundle" in methods


def test_tool_schema_all_18_actions():
    actions = GOOGLE_MEET_TOOL_SCHEMA["properties"]["action"]["enum"]
    expected_actions = [
        "join",
        "create",
        "status",
        "transcript",
        "setup_status",
        "resolve_space",
        "preflight",
        "latest",
        "calendar_events",
        "artifacts",
        "attendance",
        "export",
        "recover_current_tab",
        "leave",
        "end_active_conference",
        "speak",
        "test_speech",
        "test_listen",
    ]
    assert len(actions) == 18
    for action in expected_actions:
        assert action in actions


def test_talk_back_modes():
    assert is_talk_back_mode("agent") is True
    assert is_talk_back_mode("bidi") is True
    assert is_talk_back_mode("transcribe") is False
    assert is_talk_back_mode("passive") is False


@pytest.mark.asyncio
async def test_tool_action_status_and_lifecycle():
    runtime = GoogleMeetRuntime(config={})
    # Status
    res = await execute_google_meet_action(
        action_name="status",
        params={},
        raw_config={},
        runtime=runtime,
    )
    assert res.get("active") is False
    assert res.get("session") is None

    # Speak
    res_speak = await execute_google_meet_action(
        action_name="speak",
        params={"message": "Say exactly: I'm here and listening."},
        raw_config={},
        runtime=runtime,
    )
    assert res_speak.get("ok") is True

    # Leave
    res_leave = await execute_google_meet_action(
        action_name="leave",
        params={},
        raw_config={},
        runtime=runtime,
    )
    assert res_leave.get("ok") is True


@pytest.mark.asyncio
async def test_speech_probe_transcribe_mode_rejection():
    runtime = GoogleMeetRuntime(config={})
    # test_speech should reject mode: transcribe
    with pytest.raises(ValueError, match="test_speech requires mode: agent or bidi"):
        await runtime_probes.test_google_meet_speech(
            runtime,  # type: ignore[arg-type]
            GoogleMeetJoinRequest(
                url="https://meet.google.com/abc-defg-hij",
                mode="transcribe",
            ),
        )


@pytest.mark.asyncio
async def test_listen_probe_talk_back_mode_rejection():
    runtime = GoogleMeetRuntime(config={})
    # test_listen should reject mode: agent
    with pytest.raises(ValueError, match="test_listen requires mode: transcribe"):
        await runtime_probes.test_google_meet_listening(
            runtime,  # type: ignore[arg-type]
            GoogleMeetJoinRequest(
                url="https://meet.google.com/abc-defg-hij",
                mode="agent",
            ),
        )
