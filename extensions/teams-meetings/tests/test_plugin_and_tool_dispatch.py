"""Tests for Teams Meetings tool action dispatching and schema."""

from __future__ import annotations

import pytest

from extensions.teams_meetings.src.plugin_helpers import execute_teams_meetings_action
from extensions.teams_meetings.src.plugin_schema import TEAMS_MEETINGS_TOOL_SCHEMA
from extensions.teams_meetings.src.runtime import TeamsMeetingsRuntime


class MockBrowser:
    async def execute(self, method: str, params: dict) -> dict:
        return {
            "result": '{"inCall": true, "url": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0"}'
        }


class MockRuntimeContext:
    def __init__(self) -> None:
        self.browser = MockBrowser()


@pytest.mark.asyncio
async def test_tool_actions_dispatch() -> None:
    mock_ctx = MockRuntimeContext()
    runtime = TeamsMeetingsRuntime(config={}, runtime=mock_ctx)

    # 1. join
    join_res = await execute_teams_meetings_action(
        action_name="join",
        params={
            "url": "https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0",
            "mode": "agent",
        },
        raw_config={},
        runtime=runtime,
    )
    assert "session" in join_res
    session = join_res["session"]
    assert session.state == "active"
    assert session.url.startswith("https://teams.microsoft.com/l/meetup-join/")

    # 2. status
    status_res = await execute_teams_meetings_action(
        action_name="status",
        params={"sessionId": session.id},
        raw_config={},
        runtime=runtime,
    )
    assert status_res.get("active") is True

    # 3. speak
    speak_res = await execute_teams_meetings_action(
        action_name="speak",
        params={"sessionId": session.id, "text": "Hello Teams meeting!"},
        raw_config={},
        runtime=runtime,
    )
    assert speak_res.get("ok") is True
    assert speak_res.get("text") == "Hello Teams meeting!"

    # 4. transcript
    trans_res = await execute_teams_meetings_action(
        action_name="transcript",
        params={"sessionId": session.id},
        raw_config={},
        runtime=runtime,
    )
    assert "transcript" in trans_res

    # 5. leave
    leave_res = await execute_teams_meetings_action(
        action_name="leave",
        params={"sessionId": session.id},
        raw_config={},
        runtime=runtime,
    )
    assert leave_res.get("ok") is True

    # 6. doctor
    doc_res = await execute_teams_meetings_action(
        action_name="doctor",
        params={},
        raw_config={},
        runtime=runtime,
    )
    assert doc_res.get("ok") is True

    # 7. setup
    setup_res = await execute_teams_meetings_action(
        action_name="setup",
        params={},
        raw_config={},
        runtime=runtime,
    )
    assert setup_res.get("ok") is True


def test_tool_schema_definition() -> None:
    assert TEAMS_MEETINGS_TOOL_SCHEMA["name"] == "teams_meetings"
    assert "properties" in TEAMS_MEETINGS_TOOL_SCHEMA["parameters"]
    assert "action" in TEAMS_MEETINGS_TOOL_SCHEMA["parameters"]["required"]
