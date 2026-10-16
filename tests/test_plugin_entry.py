"""Tests for packages/plugin_sdk/src/jarvis_sdk/plugin_entry.py.

Mirrors tests of src/plugin-sdk/plugin-entry.ts in OpenClaw.
"""

from __future__ import annotations


from jarvis_sdk.plugin_entry import (
    JarvisPluginApi,
    define_channel_plugin_entry,
    define_plugin_entry,
)


def test_define_plugin_entry():
    entry = define_plugin_entry(
        id="my-plugin",
        name="My Plugin",
        description="Adds a custom tool",
    )
    assert entry.id == "my-plugin"
    assert entry.name == "My Plugin"
    assert entry.kind == "standard"


def test_define_channel_plugin_entry():
    entry = define_channel_plugin_entry(
        id="zalouser",
        name="Zalo Personal",
        description="Personal Zalo channel",
    )
    assert entry.id == "zalouser"
    assert entry.kind == "channel"


def test_plugin_api_tool_registration():
    api = JarvisPluginApi(plugin_id="my-plugin")

    async def dummy_exec(_id: str, params: dict):
        return {"content": [{"type": "text", "text": "hello"}]}

    tool = api.register_tool(
        name="my_tool",
        description="Echo input",
        parameters={"type": "object", "properties": {"input": {"type": "string"}}},
        execute=dummy_exec,
        optional=True,
    )

    assert len(api.registered_tools) == 1
    assert tool.name == "my_tool"
    assert tool.description == "Echo input"
    assert tool.optional is True
