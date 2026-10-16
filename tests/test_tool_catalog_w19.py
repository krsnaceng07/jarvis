"""Tests for Wave 19 — Tool Catalog + Tool Search."""

from __future__ import annotations


from src.agents.tool_catalog import ToolCatalog, ToolDescriptor
from src.agents.tool_search import ToolSearchRuntime
from src.agents.tool_schema_projection import project_tool_schema


def test_tool_catalog_and_search():
    cat = ToolCatalog()
    t1 = ToolDescriptor("read_file", "Read text file contents from filesystem", "core")
    t2 = ToolDescriptor("write_file", "Write text contents to file", "core")
    t3 = ToolDescriptor("weather_search", "Get weather report", "plugin", plugin_id="weather")

    cat.register(t1)
    cat.register(t2)
    cat.register(t3)

    assert len(cat.get_effective_inventory()) == 3

    # Search query
    runtime = ToolSearchRuntime(catalog=cat)
    res = runtime.search("read file")
    assert len(res) >= 1
    assert res[0]["name"] == "read_file"


def test_quarantine_and_projection():
    cat = ToolCatalog()
    t1 = ToolDescriptor("buggy_tool", "Tool with bug", "plugin", plugin_id="p1")
    cat.register(t1)

    assert cat.quarantine("buggy_tool", "Caused crash")
    assert len(cat.get_effective_inventory()) == 0

    proj = project_tool_schema(t1)
    assert proj["name"] == "buggy_tool"
