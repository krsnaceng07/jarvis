"""tests.test_realtime_tools — Unit tests for web_search tool."""

import pytest
from src.agents.sessions.tools import create_web_search_tool


@pytest.mark.asyncio
async def test_web_search_tool_execution():
    tool = create_web_search_tool()
    assert tool["name"] == "web_search"
    assert "execute" in tool

    # Query without parameter
    missing_res = await tool["execute"]("tc-1", {})
    assert "Error:" in missing_res["content"][0]["text"]
