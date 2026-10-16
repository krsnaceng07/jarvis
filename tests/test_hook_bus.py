"""Tests for packages/plugin_sdk/src/jarvis_sdk/hook_bus.py.

Mirrors tests of docs/plugins/plugin-hooks.md and src/gateway/hooks.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from jarvis_sdk.hook_bus import HOOK_CATALOG, HookBus
from jarvis_sdk.plugin_entry import JarvisPluginApi


def test_hook_catalog_count():
    assert len(HOOK_CATALOG) == 41

    assert "before_tool_call" in HOOK_CATALOG
    assert "before_prompt_build" in HOOK_CATALOG
    assert "message_received" in HOOK_CATALOG


def test_hook_bus_invalid_name():
    bus = HookBus()
    with pytest.raises(ValueError, match="Unknown plugin hook"):
        bus.on("nonexistent_hook", lambda e, c: None)


def test_hook_bus_priority_order():
    bus = HookBus()
    res = []

    bus.on("before_prompt_build", lambda e, c: res.append("low"), priority=10)
    bus.on("before_prompt_build", lambda e, c: res.append("high"), priority=100)

    handlers = bus.get_handlers("before_prompt_build")
    assert len(handlers) == 2
    assert handlers[0].priority == 100
    assert handlers[1].priority == 10


def test_hook_bus_matcher_filtering():
    bus = HookBus()

    bus.on("before_tool_call", lambda e, c: None, matcher=["web_search"])
    bus.on("before_tool_call", lambda e, c: None, matcher=["exec"])

    web_handlers = bus.get_handlers("before_tool_call", tool_name="web_search")
    assert len(web_handlers) == 1
    assert web_handlers[0].matcher == ["web_search"]


@pytest.mark.asyncio
async def test_hook_bus_pipeline_execution():
    api = JarvisPluginApi("tool-preflight")

    api.on(
        "before_tool_call",
        lambda event, ctx: {"block": True, "blockReason": "Search denied"} if event.get("toolName") == "restricted" else None,
        priority=50,
        matcher=["restricted"],
    )

    bus = api._hook_bus
    res = await bus.emit_pipeline("before_tool_call", {"toolName": "restricted", "params": {}})
    assert res == {"block": True, "blockReason": "Search denied"}
