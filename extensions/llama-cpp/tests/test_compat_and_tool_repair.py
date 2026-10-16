"""Unit tests for tool schema cleaning and chat template keyword adaptations."""

from __future__ import annotations

from extensions.llama_cpp.src.compat import (
    adapt_chat_completion_payload,
    sanitize_tool_schema,
)


def test_sanitize_tool_schema() -> None:
    raw_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.com/tool.schema.json",
        "type": "object",
        "unevaluatedProperties": False,
        "properties": {
            "query": {
                "type": "string",
                "description": "Search term",
                "unevaluatedItems": False,
            },
            "options": {
                "type": "object",
                "$defs": {},
                "properties": {
                    "limit": {"type": "integer"},
                },
            },
        },
        "required": ["query"],
    }

    cleaned = sanitize_tool_schema(raw_schema)

    # Top level stripped
    assert "$schema" not in cleaned
    assert "$id" not in cleaned
    assert "unevaluatedProperties" not in cleaned
    assert cleaned["type"] == "object"
    assert cleaned["required"] == ["query"]

    # Nested properties cleaned
    assert "unevaluatedItems" not in cleaned["properties"]["query"]
    assert "$defs" not in cleaned["properties"]["options"]
    assert cleaned["properties"]["options"]["properties"]["limit"]["type"] == "integer"


def test_adapt_chat_completion_payload() -> None:
    raw_payload = {
        "model": "qwen3.8-27b",
        "messages": [{"role": "user", "content": "Hello"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_docs",
                    "parameters": {
                        "$schema": "http://json-schema.org/draft-07/schema#",
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                },
            }
        ],
    }

    adapted = adapt_chat_completion_payload(
        raw_payload,
        is_thinking_disabled=True,
    )

    # Tool schema cleaned
    func_params = adapted["tools"][0]["function"]["parameters"]
    assert "$schema" not in func_params
    assert func_params["properties"]["query"]["type"] == "string"

    # Thinking flag mapped
    assert "chat_template_kwargs" in adapted
    assert adapted["chat_template_kwargs"]["enable_thinking"] is False
