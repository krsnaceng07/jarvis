"""tests.test_realtime_tools — Unit tests for audio, system_info, and web_search tools."""

import pytest
from src.agents.sessions.tools import (
    create_audio_tool,
    create_system_info_tool,
    create_web_search_tool,
)


@pytest.mark.asyncio
async def test_audio_tool_execution():
    tool = create_audio_tool()
    assert tool["name"] == "audio"
    assert "execute" in tool

    # 1. get_volume
    res = await tool["execute"]("tc-1", {"action": "get_volume"})
    assert "content" in res
    assert "Current Master Volume" in res["content"][0]["text"]

    # 2. invalid action
    err_res = await tool["execute"]("tc-2", {"action": "invalid_action"})
    assert "Error:" in err_res["content"][0]["text"]


@pytest.mark.asyncio
async def test_system_info_tool_execution():
    tool = create_system_info_tool()
    assert tool["name"] == "system_info"
    assert "execute" in tool

    # 1. summary
    summary_res = await tool["execute"]("tc-1", {"action": "summary"})
    assert "HOST SYSTEM SUMMARY" in summary_res["content"][0]["text"]
    assert "Clock:" in summary_res["content"][0]["text"]

    # 2. clock
    clock_res = await tool["execute"]("tc-2", {"action": "clock"})
    assert "Current Host Time" in clock_res["content"][0]["text"]
    assert "Timezone" in clock_res["content"][0]["text"]

    # 3. metrics
    metrics_res = await tool["execute"]("tc-3", {"action": "metrics"})
    assert "CPU Utilization" in metrics_res["content"][0]["text"]
    assert "RAM Memory" in metrics_res["content"][0]["text"]

    # 4. processes
    proc_res = await tool["execute"]("tc-4", {"action": "processes", "limit": 3})
    assert "Running Processes" in proc_res["content"][0]["text"]


@pytest.mark.asyncio
async def test_web_search_tool_execution():
    tool = create_web_search_tool()
    assert tool["name"] == "web_search"
    assert "execute" in tool

    # Query without parameter
    missing_res = await tool["execute"]("tc-1", {})
    assert "Error:" in missing_res["content"][0]["text"]
