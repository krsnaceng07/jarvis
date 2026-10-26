"""Desktop model-facing tool declarations."""

from __future__ import annotations

from typing import Any

from .tool_pipeline import CODING_TOOL_DECLARATIONS as _RAW_CODING_TOOL_DECLARATIONS


def normalize_model_tool_declaration(decl: dict[str, Any]) -> dict[str, Any]:
    raw_desc = decl.get("description", "")
    if isinstance(raw_desc, (list, tuple)):
        description = " ".join(str(x) for x in raw_desc)
    else:
        description = str(raw_desc or "")

    raw_params = decl.get("parameters", {})
    if isinstance(raw_params, dict):
        params = _uppercase_schema_types(raw_params)
    else:
        params = {"type": "OBJECT", "properties": {}}

    return {
        "name": str(decl.get("name") or ""),
        "description": description,
        "parameters": params,
    }


def _uppercase_schema_types(schema: Any) -> Any:
    if isinstance(schema, dict):
        result: dict[str, Any] = {}
        for key, value in schema.items():
            if key == "type" and isinstance(value, str):
                result[key] = value.upper()
            elif key == "type" and isinstance(value, list):
                result[key] = [item.upper() if isinstance(item, str) else item for item in value]
            elif key == "properties" and isinstance(value, dict):
                result[key] = {
                    pk: _uppercase_schema_types(pv)
                    for pk, pv in value.items()
                    if isinstance(pv, dict)
                }
            elif key == "items" and isinstance(value, dict):
                result[key] = _uppercase_schema_types(value)
            else:
                result[key] = _uppercase_schema_types(value)
        # CRITICAL PROTOCOL INVARIANT: Google Gemini Live requires items for every ARRAY parameter
        if result.get("type") == "ARRAY" and ("items" not in result or not result["items"]):
            result["items"] = {"type": "STRING"}
        return result
    if isinstance(schema, list):
        return [_uppercase_schema_types(item) for item in schema]
    return schema


_BASE_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "shutdown_jarvis",
        "description": (
            "CRITICAL: Terminates and exits the JARVIS desktop process on the host PC. "
            "STRICT RULES: "
            "1. ONLY call this if user EXPLICITLY commands shutdown/exit (e.g. 'shutdown jarvis', 'jarvis banda gara'). "
            "2. NEVER call this tool autonomously, after completing a task, or after saving memory. "
            "3. Both 'user_command' and 'confirmed' are strictly required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "user_command": {
                    "type": "string",
                    "description": "Exact user command requesting shutdown.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Must be true to confirm explicit user shutdown request.",
                },
            },
            "required": ["user_command", "confirmed"],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    ),
                },
                "key": {
                    "type": "string",
                    "description": "Short snake_case key (e.g. name, favorite_food, sister_name)",
                },
                "value": {
                    "type": "string",
                    "description": "Concise value in English (e.g. Fatih, pizza, older sister)",
                },
            },
            "required": ["category", "key", "value"],
        },
    },
    {
        "name": "recall_memory",
        "description": (
            "Retrieve relevant facts, user preferences, projects, directives, or historical details "
            "from JARVIS's unified hybrid semantic memory (SQLite BM25 + LanceDB vector embedding). "
            "Use this when answering questions about the user, looking up past context, or retrieving "
            "specific details not present in the immediate conversation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query or keywords to recall from memory.",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional category filter: 'identity', 'preferences', 'projects', "
                        "'relationships', 'wishes', 'notes'."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of memories to return (default: 8).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "standby_jarvis",
        "description": (
            "Put JARVIS into standby sleep mode. Call this when the user says "
            "'go to sleep', 'enter standby', 'sleep now', 'standby mode', or 'suta'. "
            "Saves API quota and pauses microphone transmission until the wake word 'Hey Jarvis' is spoken."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Optional reason for entering standby mode.",
                },
            },
        },
    },
    {
        "name": "computer",
        "description": (
            "Control native Windows desktop apps, windows, and hardware controls (Notepad, Explorer, Chrome, volume, brightness). "
            "Use browser(...) for any web page interaction instead. "
            "Actions: minimize, maximize, restore, focus_app, launch_app, close_app, close_window, kill_app, list_apps, screenshot, "
            "inspect_ui, click, right_click, double_click, move, type, key, hotkey, scroll, drag, wait, "
            "set_volume, get_volume, adjust_volume, mute, unmute, set_brightness, get_brightness, adjust_brightness."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": (
                        "Desktop action: minimize, maximize, restore, focus_app, launch_app, close_app, close_window, kill_app, "
                        "list_apps, screenshot, inspect_ui, click, right_click, double_click, "
                        "move, type, key, hotkey, scroll, drag, wait, "
                        "set_volume, get_volume, adjust_volume, mute, unmute, set_brightness, get_brightness, adjust_brightness"
                    ),
                },
                "app_name": {
                    "type": "string",
                    "description": (
                        "Application or window title for minimize/maximize/restore/focus_app/launch_app/close_app/kill_app "
                        "(e.g. 'chrome', 'youtube', 'notepad'). Omit to act on the whole desktop or active window."
                    ),
                },
                "value": {
                    "type": "integer",
                    "description": "Value or percentage (0-100) for volume or screen brightness.",
                },
                "volume": {
                    "type": "integer",
                    "description": "Target volume percentage (0-100).",
                },
                "brightness": {
                    "type": "integer",
                    "description": "Target screen brightness percentage (0-100).",
                },
                "x": {"type": "integer", "description": "Target X coordinate."},
                "y": {"type": "integer", "description": "Target Y coordinate."},
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "[x, y] target coordinate.",
                },
                "text": {"type": "string", "description": "Text to type."},
                "key": {"type": "string", "description": "Key to press."},
                "keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Key combination for hotkey (e.g. ['ctrl', 'c']).",
                },
                "delta": {
                    "type": "integer",
                    "description": "Adjustment delta for adjust_volume (+15, -15), adjust_brightness (+15, -15), or scroll delta.",
                },
                "target_id": {
                    "type": "integer",
                    "description": "Element ID from inspect_ui/screenshot annotation.",
                },
                "element_name": {
                    "type": "string",
                    "description": "Element name resolved from the last UI grounding scan.",
                },
                "annotate": {
                    "type": "boolean",
                    "description": "Render [ref] badges on the screenshot for UI grounding.",
                },
                "include_base64": {
                    "type": "boolean",
                    "description": "Include the screenshot image bytes in the result.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "browser",
        "description": (
            "Automate web browsing and DOM interaction. "
            "Use this for opening ChatGPT, searching Google, playing YouTube videos, navigating web apps, "
            "inspecting web pages with Set-of-Mark (SoM) element refs, clicking buttons/links, "
            "and typing into forms."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": (
                        "Browser action: open, navigate, google_search, youtube_play, snapshot, "
                        "click, type, press_key, scroll, extract_text, go_back, go_forward, reload, close"
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "Target URL, website name, or search query.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for google_search or youtube_play.",
                },
                "ref": {
                    "type": "integer",
                    "description": "DOM element reference ID [ref] from snapshot.",
                },
                "text": {
                    "type": "string",
                    "description": "Visible text of button/link to click, or text to type.",
                },
                "value": {
                    "type": "string",
                    "description": "Text string to type into an input field.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector or input placeholder/label hint.",
                },
                "key": {
                    "type": "string",
                    "description": "Key to press for press_key action (e.g. 'Return', 'Enter', 'Escape').",
                },
                "submit": {
                    "type": "boolean",
                    "description": "Whether to press Enter after typing (default True).",
                },
                "direction": {
                    "type": "string",
                    "description": "Scroll direction: down, up, top, bottom.",
                },
                "annotate": {
                    "type": "boolean",
                    "description": "Whether to render visual [ref] badges on the DOM.",
                },
            },
            "required": ["action"],
        },
    },
    *_RAW_CODING_TOOL_DECLARATIONS,
]


def _deduplicate_declarations(declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for decl in declarations:
        name = decl.get("name")
        if name and name not in seen:
            seen.add(name)
            deduped.append(decl)
    return deduped


CODING_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    normalize_model_tool_declaration(decl)
    for decl in _deduplicate_declarations(_RAW_CODING_TOOL_DECLARATIONS)
]

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    normalize_model_tool_declaration(decl)
    for decl in _deduplicate_declarations(_BASE_TOOL_DECLARATIONS)
]


def build_jarvis_tool_declarations(
    plugin_tools: list[dict[str, Any]] | None = None,
    host_tools: dict[str, Any] | list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Assemble and deduplicate all active tool declarations for Gemini Live."""
    all_decls = list(TOOL_DECLARATIONS)
    if plugin_tools:
        all_decls.extend(plugin_tools)
    if host_tools:
        tools_iter = host_tools.values() if isinstance(host_tools, dict) else host_tools
        for ht in tools_iter:
            decl = (
                getattr(ht, "declaration", None)
                or getattr(ht, "schema", None)
                or getattr(ht, "tool_declaration", None)
            )
            if isinstance(decl, dict):
                all_decls.append(decl)
            elif (
                isinstance(ht, dict)
                and "name" in ht
                and ("parameters" in ht or "inputSchema" in ht)
            ):
                # Some host tools carry the JSON Schema as ``inputSchema``.
                all_decls.append(
                    {**ht, "parameters": ht.get("parameters") or ht.get("inputSchema") or {}}
                )
    return [normalize_model_tool_declaration(d) for d in _deduplicate_declarations(all_decls)]


build_openclaw_tool_declarations = build_jarvis_tool_declarations

__all__ = [
    "CODING_TOOL_DECLARATIONS",
    "TOOL_DECLARATIONS",
    "build_jarvis_tool_declarations",
    "build_openclaw_tool_declarations",
    "normalize_model_tool_declaration",
]
