"""Unit tests for Zoom Meetings tool dispatch, Gateway RPCs, and CLI argument parsing."""

from __future__ import annotations

import argparse
import pytest

from extensions.zoom_meetings.plugin import ZoomMeetingsPlugin
from extensions.zoom_meetings.src.cli import register_zoom_meetings_cli
from extensions.zoom_meetings.src.config import ZoomMeetingsConfig
from extensions.zoom_meetings.src.plugin_helpers import execute_zoom_meetings_action
from extensions.zoom_meetings.src.runtime import ZoomMeetingsRuntime


@pytest.mark.asyncio
async def test_tool_action_dispatch_lifecycle() -> None:
    cfg = ZoomMeetingsConfig(enabled=True)
    runtime = ZoomMeetingsRuntime(cfg)
    raw_cfg = {"enabled": True}

    # 1. Join meeting via tool action
    res_join = await execute_zoom_meetings_action(
        action_name="join",
        params={
            "url": "https://zoom.us/j/12345678901",
            "name": "JARVIS Agent",
            "mode": "agent",
        },
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_join["ok"] is True
    session_id = res_join["sessionId"]
    assert res_join["manualAction"] is False

    # 2. Speak
    res_spk = await execute_zoom_meetings_action(
        action_name="speak",
        params={"sessionId": session_id, "message": "Speaking to participants"},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_spk["ok"] is True
    assert res_spk["spokenText"] == "Speaking to participants"

    # 3. Transcript
    res_tr = await execute_zoom_meetings_action(
        action_name="transcript",
        params={"sessionId": session_id},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_tr["ok"] is True
    assert len(res_tr["transcript"]) >= 1

    # 4. Status
    res_st = await execute_zoom_meetings_action(
        action_name="status",
        params={"sessionId": session_id},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_st["active"] is True
    assert res_st["session"]["id"] == session_id

    # 5. Leave
    res_lv = await execute_zoom_meetings_action(
        action_name="leave",
        params={"sessionId": session_id},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_lv["ok"] is True
    assert res_lv["status"] == "ended"


@pytest.mark.asyncio
async def test_manual_action_dispatch() -> None:
    cfg = ZoomMeetingsConfig(enabled=True)
    runtime = ZoomMeetingsRuntime(cfg)
    raw_cfg = {"enabled": True}

    # Join with waiting room policy text
    res_join = await execute_zoom_meetings_action(
        action_name="join",
        params={
            "url": "https://zoom.us/j/12345678901",
            "simulatedPageText": "Please wait, the meeting host will let you in soon.",
        },
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_join["ok"] is True
    assert res_join["manualAction"] is True
    assert res_join["manualActionReason"] == "waiting_room_host_admission"
    assert "Waiting Room" in res_join["manualActionMessage"]


@pytest.mark.asyncio
async def test_plugin_registration() -> None:
    plugin = ZoomMeetingsPlugin()
    tools = plugin.register_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "zoom_meetings"

    rpcs = plugin.register_rpc_methods()
    assert "zoommeetings.join" in rpcs
    assert "zoommeetings.leave" in rpcs
    assert "zoommeetings.status" in rpcs
    assert "zoommeetings.transcript" in rpcs
    assert "zoommeetings.speak" in rpcs
    assert "zoommeetings.setup" in rpcs
    assert "zoommeetings.doctor" in rpcs


def test_cli_parser_registration() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand")
    cmd_p = register_zoom_meetings_cli(subparsers)
    assert cmd_p is not None

    # Parse join command
    args_join = parser.parse_args(
        [
            "zoommeetings",
            "join",
            "https://zoom.us/j/123456789",
            "--name",
            "JARVIS",
            "--mode",
            "agent",
        ]
    )
    assert args_join.zoommeetings_action == "join"
    assert args_join.url == "https://zoom.us/j/123456789"
    assert args_join.name == "JARVIS"
    assert args_join.mode == "agent"

    # Parse speak command
    args_spk = parser.parse_args(["zoommeetings", "speak", "session_123", "--message", "Hello"])
    assert args_spk.zoommeetings_action == "speak"
    assert args_spk.session_id == "session_123"
    assert args_spk.message == "Hello"

    # Parse setup command
    args_setup = parser.parse_args(["zoommeetings", "setup", "--json"])
    assert args_setup.zoommeetings_action == "setup"
    assert args_setup.json is True
