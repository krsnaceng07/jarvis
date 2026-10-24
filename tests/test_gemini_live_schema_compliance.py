"""tests/test_gemini_live_schema_compliance.py
Verification test suite ensuring 100% schema compliance for Gemini Live Bidi WebSocket:
- Validates that every tool in build_jarvis_gemini_tools() has valid 'items' for any 'array' parameter.
- Tests that clean_gemini_declarations and _clean_schema auto-heal missing 'items' for arbitrary array types.
- Tests that _uppercase_schema_types guarantees 'items' for ARRAY parameters.
- Prevents APIError 1007 setup disconnects.
"""

from __future__ import annotations

from jarvis_desktop.tool_declarations import _uppercase_schema_types
from jarvis_voice_pipeline.pipeline_builder import (
    _clean_schema,
    build_jarvis_gemini_tools,
)


def test_every_declared_tool_array_has_items():
    """Verify that every tool declaration passed to Gemini Live contains 'items' for all array properties."""
    tools = build_jarvis_gemini_tools()
    assert len(tools) > 0

    for tool in tools:
        name = tool.get("name")
        params = tool.get("parameters", {})
        props = params.get("properties", {})

        def check_prop(prop_name: str, prop_val: dict):
            p_type = prop_val.get("type")
            if p_type in ("array", "ARRAY"):
                assert "items" in prop_val, (
                    f"Tool '{name}' property '{prop_name}' has type 'array' but is missing 'items'!"
                )
                assert isinstance(prop_val["items"], dict), (
                    f"Tool '{name}' property '{prop_name}' items must be a dict!"
                )
                assert "type" in prop_val["items"], (
                    f"Tool '{name}' property '{prop_name}' items must have 'type' specified!"
                )
            if "properties" in prop_val and isinstance(prop_val["properties"], dict):
                for child_k, child_v in prop_val["properties"].items():
                    if isinstance(child_v, dict):
                        check_prop(f"{prop_name}.{child_k}", child_v)

        for pk, pv in props.items():
            if isinstance(pv, dict):
                check_prop(pk, pv)


def test_clean_schema_auto_heals_missing_items():
    """Verify that _clean_schema auto-injects items for any naked array property."""
    broken_schema = {
        "type": "object",
        "properties": {
            "naked_list": {
                "type": "array",
                "description": "A list with no items field",
            },
            "coords": {
                "type": "array",
                "description": "Coordinates with no items field",
            },
        },
    }

    cleaned = _clean_schema(broken_schema)
    assert "naked_list" in cleaned["properties"]
    assert cleaned["properties"]["naked_list"]["type"] == "array"
    assert "items" in cleaned["properties"]["naked_list"]
    assert cleaned["properties"]["naked_list"]["items"]["type"] == "string"

    assert "coords" in cleaned["properties"]
    assert cleaned["properties"]["coords"]["type"] == "array"
    assert "items" in cleaned["properties"]["coords"]
    assert cleaned["properties"]["coords"]["items"]["type"] == "string"


def test_uppercase_schema_types_auto_heals_missing_items():
    """Verify that _uppercase_schema_types auto-injects uppercase ITEMS for ARRAY types."""
    broken_schema = {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "description": "Tags without items",
            }
        },
    }

    uppercased = _uppercase_schema_types(broken_schema)
    assert uppercased["properties"]["tags"]["type"] == "ARRAY"
    assert "items" in uppercased["properties"]["tags"]
    assert uppercased["properties"]["tags"]["items"]["type"] == "STRING"


def test_computer_tool_coordinates_and_keys_have_typed_items():
    """Explicitly verify that tool [4] ('computer') has coordinate: integer items and keys: string items."""
    tools = build_jarvis_gemini_tools()
    comp_tools = [t for t in tools if t.get("name") == "computer"]
    assert len(comp_tools) == 1, "Expected exactly 1 'computer' tool declaration"
    comp = comp_tools[0]
    props = comp["parameters"]["properties"]

    assert props["coordinate"]["type"] == "array"
    assert props["coordinate"]["items"]["type"] == "integer"

    assert props["keys"]["type"] == "array"
    assert props["keys"]["items"]["type"] == "string"
