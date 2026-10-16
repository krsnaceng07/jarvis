"""Unit tests for Voice Call plugin tool dispatch, gateway RPCs, and CLI parsing."""

from __future__ import annotations

import argparse
import pytest

from extensions.voice_call.plugin import VoiceCallPlugin
from extensions.voice_call.src.cli import register_voice_call_cli
from extensions.voice_call.src.config import VoiceCallConfig
from extensions.voice_call.src.plugin_helpers import execute_voice_call_action
from extensions.voice_call.src.runtime import VoiceCallRuntime


@pytest.mark.asyncio
async def test_tool_action_dispatch() -> None:
    cfg = VoiceCallConfig(enabled=True, provider="mock")
    runtime = VoiceCallRuntime(cfg)
    raw_cfg = {"enabled": True, "provider": "mock"}

    # 1. Initiate call via tool
    res_call = await execute_voice_call_action(
        action_name="call",
        params={"to": "+15555550123", "message": "Testing tool call"},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_call["ok"] is True
    call_id = res_call["callId"]

    # 2. Speak
    res_spk = await execute_voice_call_action(
        action_name="speak",
        params={"callId": call_id, "text": "Speaking to user"},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_spk["ok"] is True

    # 3. DTMF
    res_dtmf = await execute_voice_call_action(
        action_name="dtmf",
        params={"callId": call_id, "digits": "99#"},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_dtmf["ok"] is True
    assert res_dtmf["digits"] == "99#"

    # 4. Status
    res_stat = await execute_voice_call_action(
        action_name="status",
        params={"callId": call_id},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_stat["active"] is True
    assert res_stat["session"]["id"] == call_id

    # 5. End
    res_end = await execute_voice_call_action(
        action_name="end",
        params={"callId": call_id},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_end["ok"] is True


@pytest.mark.asyncio
async def test_plugin_registration_and_rpc() -> None:
    plugin = VoiceCallPlugin()
    tools = plugin.register_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "voice_call"

    rpcs = plugin.register_rpc_methods()
    assert "voicecall.initiate" in rpcs
    assert "voicecall.status" in rpcs
    assert "voicecall.speak" in rpcs
    assert "voicecall.end" in rpcs
    assert "voicecall.setup" in rpcs


def test_cli_parser_registration() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand")
    cmd_p = register_voice_call_cli(subparsers)
    assert cmd_p is not None

    # Parse call command
    args_call = parser.parse_args(["voicecall", "call", "+15555550123", "--message", "Hello"])
    assert args_call.voicecall_action == "call"
    assert args_call.to == "+15555550123"
    assert args_call.message == "Hello"

    # Parse start command (alias with dtmf-sequence)
    args_start = parser.parse_args(
        ["voicecall", "start", "+15555550123", "--dtmf-sequence", "1234#"]
    )
    assert args_start.voicecall_action == "start"
    assert args_start.dtmf_sequence == "1234#"

    # Parse setup command
    args_setup = parser.parse_args(["voicecall", "setup", "--json"])
    assert args_setup.voicecall_action == "setup"
    assert args_setup.json is True

    # Parse latency command
    args_lat = parser.parse_args(["voicecall", "latency", "--last", "50", "--json"])
    assert args_lat.voicecall_action == "latency"
    assert args_lat.last == 50

    # Parse expose command
    args_exp = parser.parse_args(["voicecall", "expose", "--mode", "funnel"])
    assert args_exp.voicecall_action == "expose"
    assert args_exp.mode == "funnel"


@pytest.mark.asyncio
async def test_dtmf_sequence_validation_and_async_continue() -> None:
    cfg = VoiceCallConfig(enabled=True, provider="mock")
    runtime = VoiceCallRuntime(cfg)
    raw_cfg = {"enabled": True, "provider": "mock"}

    # 1. dtmfSequence with invalid mode (notify) should fail
    res_bad = await execute_voice_call_action(
        action_name="voicecall.start",
        params={
            "to": "+15555550123",
            "mode": "notify",
            "dtmfSequence": "123#",
        },
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_bad["ok"] is False
    assert "dtmfSequence is only valid with mode: 'conversation'" in res_bad["error"]

    # 2. dtmfSequence with valid mode (conversation)
    res_ok = await execute_voice_call_action(
        action_name="voicecall.start",
        params={
            "to": "+15555550123",
            "mode": "conversation",
            "dtmfSequence": "123#",
        },
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_ok["ok"] is True
    call_id = res_ok["callId"]

    # 3. voicecall.continue.start (async variant)
    res_async_start = await execute_voice_call_action(
        action_name="voicecall.continue.start",
        params={"callId": call_id, "message": "Async continue message"},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_async_start["ok"] is True
    assert "operationId" in res_async_start
    op_id = res_async_start["operationId"]

    # 4. voicecall.continue.result (poll result)
    import asyncio

    await asyncio.sleep(0.05)  # Let background task complete
    res_async_result = await execute_voice_call_action(
        action_name="voicecall.continue.result",
        params={"operationId": op_id},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_async_result["ok"] is True
    assert res_async_result["status"] == "completed"

    # 5. voicecall.status without callId lists all active calls
    res_all = await execute_voice_call_action(
        action_name="voicecall.status",
        params={},
        raw_config=raw_cfg,
        runtime=runtime,
    )
    assert res_all["ok"] is True
    assert "activeCalls" in res_all
    assert res_all["count"] >= 1
    assert any(c["id"] == call_id for c in res_all["activeCalls"])
