"""Canvas agent tool definition and execution."""

from __future__ import annotations

from typing import Any
import uuid

from .a2ui_jsonl import parse_a2ui_jsonl


async def execute_canvas_tool(params: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Execute the canvas presentation tool."""
    action = str(params.get("action", "present")).lower()
    target = params.get("target", "default")
    content = params.get("content")
    url = params.get("url")
    widget_id = params.get("widgetId") or str(uuid.uuid4())

    if action == "present":
        if url:
            return {
                "content": [
                    {"type": "text", "text": f"Presented URL on canvas target '{target}': {url}"}
                ],
                "details": {
                    "action": "present",
                    "target": target,
                    "url": url,
                    "widgetId": widget_id,
                },
            }
        if content:
            if isinstance(content, str) and ("{" in content or "[" in content):
                events = parse_a2ui_jsonl(content)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Presented interactive A2UI widget on canvas '{target}' ({len(events)} events)",
                        }
                    ],
                    "details": {
                        "action": "present",
                        "target": target,
                        "eventCount": len(events),
                        "widgetId": widget_id,
                    },
                }
            return {
                "content": [
                    {"type": "text", "text": f"Presented content on canvas target '{target}'"}
                ],
                "details": {"action": "present", "target": target, "widgetId": widget_id},
            }
        return {"error": "Missing 'content' or 'url' to present on canvas."}

    if action == "hide":
        return {
            "content": [{"type": "text", "text": f"Hidden canvas target '{target}'"}],
            "details": {"action": "hide", "target": target, "widgetId": widget_id},
        }

    if action in ("update", "eval"):
        return {
            "content": [{"type": "text", "text": f"Canvas target '{target}' {action} executed"}],
            "details": {"action": action, "target": target, "widgetId": widget_id},
        }

    return {"error": f"Unknown canvas action: {action}"}


def register_canvas_tool(api: Any) -> None:
    """Register canvas tool with plugin API."""
    if hasattr(api, "register_tool"):
        api.register_tool(
            name="canvas",
            description="Present interactive widgets, web pages, or A2UI streams on canvas panels.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "action": {
                        "type": "STRING",
                        "enum": ["present", "hide", "update", "eval"],
                        "description": "Canvas action to perform.",
                    },
                    "target": {"type": "STRING", "description": "Canvas target panel."},
                    "content": {
                        "type": "STRING",
                        "description": "HTML or A2UI JSONL widget content.",
                    },
                    "url": {"type": "STRING", "description": "Web URL to present on canvas."},
                    "widgetId": {"type": "STRING", "description": "Optional widget identifier."},
                },
            },
            execute=execute_canvas_tool,
        )
