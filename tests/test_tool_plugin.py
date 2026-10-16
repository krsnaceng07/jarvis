"""Tests for packages/plugin_sdk/src/jarvis_sdk/tool_plugin.py.

Mirrors tests of src/plugin-sdk/tool-plugin.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from jarvis_sdk.plugin_entry import JarvisPluginApi
from jarvis_sdk.tool_plugin import define_tool_plugin, format_tool_result


def test_format_tool_result_str():
    res = format_tool_result("Hello World")
    assert res == {"content": [{"type": "text", "text": "Hello World"}], "details": "Hello World"}


def test_format_tool_result_dict():
    res = format_tool_result({"symbol": "OPEN", "configured": True})
    assert res["details"] == {"symbol": "OPEN", "configured": True}
    assert "content" in res


def test_define_tool_plugin():
    plugin_def = define_tool_plugin(
        id="stock-quotes",
        name="Stock Quotes",
        description="Fetch stock quotes",
        tools=lambda tool: [
            tool(
                name="stock_quote",
                description="Fetch stock quote snapshot",
                parameters={"type": "object", "properties": {"symbol": {"type": "string"}}},
                execute=lambda p: {"symbol": p["symbol"].upper(), "price": 100},
            )
        ],
    )

    assert plugin_def.id == "stock-quotes"
    assert len(plugin_def.declared_tools) == 1
    assert plugin_def.declared_tools[0].name == "stock_quote"

    api = JarvisPluginApi("stock-quotes")
    if plugin_def.register_fn:
        plugin_def.register_fn(api)

    assert len(api.registered_tools) == 1
    assert api.registered_tools[0].name == "stock_quote"


@pytest.mark.asyncio
async def test_tool_plugin_execution_wrapper():
    plugin_def = define_tool_plugin(
        id="echo-plugin",
        name="Echo Plugin",
        description="Echo input",
        tools=lambda tool: [
            tool(
                name="echo_text",
                description="Echo text",
                parameters={"type": "object"},
                execute=lambda p: f"Got: {p.get('input')}",
            )
        ],
    )

    api = JarvisPluginApi("echo-plugin")
    if plugin_def.register_fn:
        plugin_def.register_fn(api)

    tool = api.registered_tools[0]
    exec_res = await tool.execute("call_1", {"input": "test_val"})
    assert exec_res["content"][0]["text"] == "Got: test_val"
