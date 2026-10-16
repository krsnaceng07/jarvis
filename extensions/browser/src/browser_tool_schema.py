"""JSON schema and result types for the Browser agent tool.

Mirrors OpenClaw's ``extensions/browser/src/browser-tool.schema.ts``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel

BrowserAction = Literal[
    "doctor",
    "status",
    "start",
    "stop",
    "profiles",
    "importprofile",
    "tabs",
    "open",
    "focus",
    "close",
    "snapshot",
    "screenshot",
    "navigate",
    "console",
    "requests",
    "errors",
    "text",
    "emulate",
    "pdf",
    "download",
    "waitfordownload",
    "upload",
    "dialog",
    "act",
    "click",
    "clickCoords",
    "type",
    "press",
    "hover",
    "scrollIntoView",
    "drag",
    "select",
    "fill",
    "resize",
    "wait",
    "evaluate",
    "app",
    "youtube",
    "web",
]

BROWSER_ACTIONS: list[str] = [
    "doctor",
    "status",
    "start",
    "stop",
    "profiles",
    "importprofile",
    "tabs",
    "open",
    "focus",
    "close",
    "snapshot",
    "screenshot",
    "navigate",
    "console",
    "requests",
    "errors",
    "text",
    "emulate",
    "pdf",
    "download",
    "waitfordownload",
    "upload",
    "dialog",
    "act",
    "click",
    "clickCoords",
    "type",
    "press",
    "hover",
    "scrollIntoView",
    "drag",
    "select",
    "fill",
    "resize",
    "wait",
    "evaluate",
    "app",
    "youtube",
    "web",
]

BrowserActKind = Literal[
    "batch",
    "click",
    "clickCoords",
    "type",
    "press",
    "hover",
    "scrollIntoView",
    "drag",
    "select",
    "fill",
    "resize",
    "wait",
    "evaluate",
    "close",
]

BROWSER_ACT_KINDS: list[str] = [
    "batch",
    "click",
    "clickCoords",
    "type",
    "press",
    "hover",
    "scrollIntoView",
    "drag",
    "select",
    "fill",
    "resize",
    "wait",
    "evaluate",
    "close",
]


@dataclass(frozen=True, slots=True)
class TextContent:
    """Textual content returned in an AgentToolResult."""

    text: str
    type: str = "text"


@dataclass(frozen=True, slots=True)
class ImageContent:
    """Image content returned in an AgentToolResult."""

    data: str  # Base64-encoded string
    mime_type: str = "image/png"
    type: str = "image"


@dataclass(frozen=True, slots=True)
class AgentToolResult:
    """Agent tool outcome returned to the runtime loop."""

    content: list[TextContent | ImageContent] = field(default_factory=list)
    details: Any = None
    progress: Any = None
    terminate: bool | None = None


def json_result(payload: Any) -> AgentToolResult:
    """Convert a dictionary or primitive payload into an AgentToolResult."""
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, indent=2, ensure_ascii=False)
    details = payload if isinstance(payload, dict) else {"result": payload}
    return AgentToolResult(
        content=[TextContent(text=text)],
        details=details,
    )


def image_result(
    image_base64: str,
    mime_type: str = "image/png",
    details: Any = None,
) -> AgentToolResult:
    """Return image data alongside structured details."""
    det = details or {"ok": True, "format": mime_type}
    text_summary = json.dumps(det, indent=2, ensure_ascii=False)
    return AgentToolResult(
        content=[
            ImageContent(data=image_base64, mime_type=mime_type),
            TextContent(text=text_summary),
        ],
        details=det,
    )


def get_browser_tool_schema() -> dict[str, Any]:
    """Return the JSON Schema dictionary for the Browser tool.

    Mirrors OpenClaw's ``createBrowserToolSchema()``.
    """
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": BROWSER_ACTIONS,
                "description": "The browser action to execute.",
            },
            "target": {
                "type": "string",
                "enum": ["sandbox", "host", "node"],
                "description": "Execution target environment.",
            },
            "node": {
                "type": "string",
                "description": "Specific node identifier when target is 'node'.",
            },
            "profile": {
                "type": "string",
                "description": "Browser profile to use; omit for configured default.",
            },
            "browser": {
                "type": "string",
                "description": "Specific browser executable or flavor.",
            },
            "targetUrl": {
                "type": "string",
                "description": "URL to open or navigate to.",
            },
            "url": {
                "type": "string",
                "description": "Alias for targetUrl.",
            },
            "targetId": {
                "type": "string",
                "description": "Target tab ID to operate on; omit for active tab.",
            },
            "label": {
                "type": "string",
                "description": "Label for tab.",
            },
            "limit": {
                "type": "integer",
                "description": "Limit count of items.",
            },
            "maxChars": {
                "type": "integer",
                "description": "Maximum characters in snapshot.",
            },
            "mode": {
                "type": "string",
                "enum": ["efficient"],
                "description": "Snapshot capture mode.",
            },
            "snapshotFormat": {
                "type": "string",
                "enum": ["aria", "ai"],
                "description": "Format of the snapshot (aria tree or simplified ai format).",
            },
            "refs": {
                "type": "string",
                "enum": ["role", "aria"],
                "description": "Reference strategy for snapshot elements.",
            },
            "interactive": {
                "type": "boolean",
                "description": "Whether to filter snapshot to only interactive elements.",
            },
            "compact": {
                "type": "boolean",
                "description": "Compact snapshot output.",
            },
            "depth": {
                "type": "integer",
                "description": "Max DOM tree depth for snapshot.",
            },
            "selector": {
                "type": "string",
                "description": "CSS selector to target.",
            },
            "frame": {
                "type": "string",
                "description": "Frame selector.",
            },
            "fullPage": {
                "type": "boolean",
                "description": "Whether to capture full page screenshot.",
            },
            "path": {
                "type": "string",
                "description": "File path to save screenshot or PDF to.",
            },
            "element": {
                "type": "string",
                "description": "Element selector for screenshot.",
            },
            "type": {
                "type": "string",
                "enum": ["png", "jpeg"],
                "description": "Image format for screenshot.",
            },
            "ref": {
                "type": "string",
                "description": "Element reference ID from snapshot (e.g. 'e1', 'e2').",
            },
            "text": {
                "type": "string",
                "description": "Text to type or fill.",
            },
            "key": {
                "type": "string",
                "description": "Key name to press (e.g. 'Enter', 'Tab').",
            },
            "x": {
                "type": "number",
                "description": "X coordinate for clickCoords.",
            },
            "y": {
                "type": "number",
                "description": "Y coordinate for clickCoords.",
            },
            "timeoutMs": {
                "type": "integer",
                "description": "Operation timeout in milliseconds.",
            },
            "kind": {
                "type": "string",
                "enum": BROWSER_ACT_KINDS,
                "description": "Interaction kind when action is 'act'.",
            },
            "fn": {
                "type": "string",
                "description": "JavaScript function body to evaluate.",
            },
            "request": {
                "type": "object",
                "description": "Structured act request object.",
            },
            "app": {
                "type": "string",
                "description": "Application adapter name when action is 'app' (e.g. 'youtube').",
            },
            "command": {
                "type": "string",
                "description": "Application command to execute (e.g. 'search', 'play_first_result', 'search_and_play', 'pause', 'resume', 'skip_ad', 'volume_up', 'volume_down', 'status').",
            },
            "query": {
                "type": "string",
                "description": "Search or playback query for application command.",
            },
        },
        "required": ["action"],
    }


def get_browser_tool_output_schema() -> dict[str, Any]:
    """Return JSON Schema for Browser tool output.

    Mirrors OpenClaw's ``BrowserToolOutputSchema``.
    """
    return {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "targetId": {"type": "string"},
            "url": {"type": "string"},
            "title": {"type": "string"},
            "format": {"type": "string"},
            "snapshot": {"type": "string"},
            "refs": {"type": "object"},
            "stats": {
                "type": "object",
                "properties": {
                    "lines": {"type": "integer"},
                    "chars": {"type": "integer"},
                    "refs": {"type": "integer"},
                    "interactive": {"type": "integer"},
                },
            },
            "tabs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "targetId": {"type": "string"},
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "active": {"type": "boolean"},
                    },
                },
            },
            "tabCount": {"type": "integer"},
            "running": {"type": "boolean"},
            "profile": {"type": "string"},
            "driver": {"type": "string"},
            "cdpPort": {"type": ["integer", "null"]},
            "error": {"type": "string"},
        },
    }


# Backward-compatible Pydantic models
class BrowserActSchema(BaseModel):
    kind: BrowserActKind
    targetId: Optional[str] = None
    ref: Optional[str] = None
    actions: Optional[List[Dict[str, Any]]] = None
    stopOnError: Optional[bool] = None
    doubleClick: Optional[bool] = None
    button: Optional[str] = None
    modifiers: Optional[List[str]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    text: Optional[str] = None
    submit: Optional[bool] = None
    slowly: Optional[bool] = None
    key: Optional[str] = None
    delayMs: Optional[int] = None
    startRef: Optional[str] = None
    endRef: Optional[str] = None
    values: Optional[List[str]] = None
    fields: Optional[List[Dict[str, Any]]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    timeMs: Optional[int] = None
    selector: Optional[str] = None
    url: Optional[str] = None
    loadState: Optional[str] = None
    textGone: Optional[str] = None
    timeoutMs: Optional[int] = None
    fn: Optional[str] = None


class BrowserToolInput(BaseModel):
    action: BrowserAction
    target: Optional[Literal["sandbox", "host", "node"]] = None
    node: Optional[str] = None
    profile: Optional[str] = None
    browser: Optional[str] = None
    systemProfile: Optional[str] = None
    into: Optional[str] = None
    domains: Optional[List[str]] = None
    targetUrl: Optional[str] = None
    url: Optional[str] = None
    targetId: Optional[str] = None
    label: Optional[str] = None
    limit: Optional[int] = None
    maxChars: Optional[int] = None
    mode: Optional[Literal["efficient"]] = None
    snapshotFormat: Optional[Literal["aria", "ai"]] = None
    refs: Optional[Literal["role", "aria"]] = None
    interactive: Optional[bool] = None
    compact: Optional[bool] = None
    depth: Optional[int] = None
    selector: Optional[str] = None
    frame: Optional[str] = None
    labels: Optional[bool] = None
    urls: Optional[bool] = None
    fullPage: Optional[bool] = None
    ref: Optional[str] = None
    path: Optional[str] = None
    element: Optional[str] = None
    type: Optional[Literal["png", "jpeg"]] = None
    level: Optional[str] = None
    paths: Optional[List[str]] = None
    inputRef: Optional[str] = None
    timeoutMs: Optional[int] = None
    dialogId: Optional[str] = None
    accept: Optional[bool] = None
    promptText: Optional[str] = None

    # Act fields
    kind: Optional[BrowserActKind] = None
    actions: Optional[List[Dict[str, Any]]] = None
    stopOnError: Optional[bool] = None
    doubleClick: Optional[bool] = None
    button: Optional[str] = None
    modifiers: Optional[List[str]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    text: Optional[str] = None
    submit: Optional[bool] = None
    slowly: Optional[bool] = None
    key: Optional[str] = None
    delayMs: Optional[int] = None
    startRef: Optional[str] = None
    endRef: Optional[str] = None
    values: Optional[List[str]] = None
    fields: Optional[List[Dict[str, Any]]] = None
    width: Optional[int] = None
    height: Optional[int] = None
    timeMs: Optional[int] = None
    textGone: Optional[str] = None
    loadState: Optional[str] = None
    fn: Optional[str] = None

    request: Optional[BrowserActSchema] = None
