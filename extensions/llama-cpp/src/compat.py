"""Compatibility transformations, tool schema cleanup, and thinking flag mappings for llama.cpp."""

from __future__ import annotations

from typing import Any


def sanitize_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Clean unsupported JSON Schema constraints for llama-server compatibility."""
    if not isinstance(schema, dict):
        return {}

    cleaned = dict(schema)

    # Remove unsupported schema metadata keywords
    unsupported_keys = [
        "$schema",
        "$id",
        "unevaluatedProperties",
        "unevaluatedItems",
        "definitions",
        "$defs",
    ]
    for key in unsupported_keys:
        cleaned.pop(key, None)

    # Clean properties recursively
    props = cleaned.get("properties")
    if isinstance(props, dict):
        cleaned_props = {}
        for prop_name, prop_val in props.items():
            if isinstance(prop_val, dict):
                cleaned_props[prop_name] = sanitize_tool_schema(prop_val)
            else:
                cleaned_props[prop_name] = prop_val
        cleaned["properties"] = cleaned_props

    # Clean items if array
    items = cleaned.get("items")
    if isinstance(items, dict):
        cleaned["items"] = sanitize_tool_schema(items)

    return cleaned


def adapt_chat_completion_payload(
    payload: dict[str, Any],
    *,
    is_thinking_disabled: bool = False,
    model_family: str = "qwen",
) -> dict[str, Any]:
    """Adapt completion request payload for llama-server backend features.

    - Cleans tool function parameters
    - Injects chat_template_kwargs for thinking flags (e.g. enable_thinking: false)
    """
    adapted = dict(payload)

    # 1. Clean tool definitions
    tools = adapted.get("tools")
    if isinstance(tools, list):
        cleaned_tools = []
        for tool in tools:
            if isinstance(tool, dict):
                t_copy = dict(tool)
                func = t_copy.get("function")
                if isinstance(func, dict):
                    f_copy = dict(func)
                    params = f_copy.get("parameters")
                    if isinstance(params, dict):
                        f_copy["parameters"] = sanitize_tool_schema(params)
                    t_copy["function"] = f_copy
                cleaned_tools.append(t_copy)
            else:
                cleaned_tools.append(tool)
        adapted["tools"] = cleaned_tools

    # 2. Map thinking-off requests to Qwen/DeepSeek template kwargs
    if is_thinking_disabled:
        if "chat_template_kwargs" not in adapted:
            adapted["chat_template_kwargs"] = {}
        adapted["chat_template_kwargs"]["enable_thinking"] = False

    return adapted
