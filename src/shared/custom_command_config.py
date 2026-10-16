"""jarvis.shared.custom_command_config — custom slash-command helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/custom-command-config.ts``.
"""
from __future__ import annotations

import re
from typing import List, Set, TypedDict

_DEFAULT_PREFIX = "/"


def normalize_slash_command_name(value: str) -> str:
    """Normalize a slash-command name to the internal lowercase-underscore form.

    Mirrors :func:`normalizeSlashCommandName`
    (``shared/custom-command-config.ts``).
    """
    if not isinstance(value, str):
        return ""
    trimmed = value.strip()
    if not trimmed:
        return ""
    without = trimmed[1:] if trimmed.startswith(_DEFAULT_PREFIX) else trimmed
    return without.lower().replace("-", "_")


def normalize_command_description(value: str) -> str:
    """Normalize a command description without changing user-authored wording.

    Mirrors :func:`normalizeCommandDescription`
    (``shared/custom-command-config.ts``).
    """
    if not isinstance(value, str):
        return ""
    return value.strip()


class CustomCommandConfigPolicy(TypedDict, total=False):
    label: str
    pattern: str
    patternDescription: str
    prefix: str


def _compile_pattern(pattern) -> "re.Pattern[str]":
    if hasattr(pattern, "match"):
        return pattern
    return re.compile(pattern)


def resolve_custom_commands(params: dict) -> dict:
    """Validate and normalize custom command config entries.

    Mirrors :func:`resolveCustomCommands` (``shared/custom-command-config.ts``).
    """
    entries = params.get("commands") or []
    if not isinstance(entries, list):
        entries = []
    reserved: Set[str] = params.get("reservedCommands") or set()
    check_reserved = params.get("checkReserved", True) is not False
    check_duplicates = params.get("checkDuplicates", True) is not False
    config = params.get("config") or {}
    pattern = _compile_pattern(config.get("pattern") or r"^[a-z][a-z0-9_]*$")
    label = config.get("label") or "Custom"
    prefix = config.get("prefix") or _DEFAULT_PREFIX

    seen: Set[str] = set()
    resolved: List[dict] = []
    issues: List[dict] = []

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            entry = {}
        normalized = normalize_slash_command_name(entry.get("command") or "")
        if not normalized:
            issues.append({
                "index": index,
                "field": "command",
                "message": f"{label} custom command is missing a command name.",
            })
            continue
        if not pattern.match(normalized):
            issues.append({
                "index": index,
                "field": "command",
                "message": (
                    f"{label} custom command \"{prefix}{normalized}\" is invalid "
                    f"({config.get('patternDescription') or 'invalid'})."
                ),
            })
            continue
        if check_reserved and normalized in reserved:
            issues.append({
                "index": index,
                "field": "command",
                "message": (
                    f"{label} custom command \"{prefix}{normalized}\" conflicts "
                    "with a native command."
                ),
            })
            continue
        if check_duplicates and normalized in seen:
            issues.append({
                "index": index,
                "field": "command",
                "message": f"{label} custom command \"{prefix}{normalized}\" is duplicated.",
            })
            continue
        description = normalize_command_description(entry.get("description") or "")
        if not description:
            issues.append({
                "index": index,
                "field": "description",
                "message": (
                    f"{label} custom command \"{prefix}{normalized}\" is missing a description."
                ),
            })
            continue
        if check_duplicates:
            seen.add(normalized)
        resolved.append({"command": normalized, "description": description})

    return {"commands": resolved, "issues": issues}


__all__ = [
    "normalize_slash_command_name",
    "normalize_command_description",
    "resolve_custom_commands",
]
