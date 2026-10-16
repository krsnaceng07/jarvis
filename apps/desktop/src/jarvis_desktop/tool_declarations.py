"""Desktop model-facing tool declarations."""

from __future__ import annotations

from typing import Any

from .tool_pipeline import CODING_TOOL_DECLARATIONS as _RAW_CODING_TOOL_DECLARATIONS


def normalize_model_tool_declaration(decl: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(decl)
    normalized["parameters"] = _uppercase_schema_types(decl.get("parameters", {}))
    return normalized


def _uppercase_schema_types(schema: Any) -> Any:
    if isinstance(schema, dict):
        result: dict[str, Any] = {}
        for key, value in schema.items():
            if key == "type" and isinstance(value, str):
                result[key] = value.upper()
            elif key == "type" and isinstance(value, list):
                result[key] = [item.upper() if isinstance(item, str) else item for item in value]
            else:
                result[key] = _uppercase_schema_types(value)
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
            "type": "OBJECT",
            "properties": {
                "user_command": {
                    "type": "STRING",
                    "description": "Exact user command requesting shutdown.",
                },
                "confirmed": {
                    "type": "BOOLEAN",
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
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
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
                    "type": "STRING",
                    "description": "Short snake_case key (e.g. name, favorite_food, sister_name)",
                },
                "value": {
                    "type": "STRING",
                    "description": "Concise value in English (e.g. Fatih, pizza, older sister)",
                },
            },
            "required": ["category", "key", "value"],
        },
    },
    *_RAW_CODING_TOOL_DECLARATIONS,
]


CODING_TOOL_DECLARATIONS: list[dict[str, Any]] = [
    normalize_model_tool_declaration(decl) for decl in _RAW_CODING_TOOL_DECLARATIONS
]

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    normalize_model_tool_declaration(decl) for decl in _BASE_TOOL_DECLARATIONS
]


__all__ = [
    "CODING_TOOL_DECLARATIONS",
    "TOOL_DECLARATIONS",
    "normalize_model_tool_declaration",
]
