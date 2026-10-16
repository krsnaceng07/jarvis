"""CUA Computer action and key normalization.

OpenClaw parity: mirrors extensions/cua-computer/src/actions.ts.
"""

from __future__ import annotations

import sys

MODIFIER_ALIASES: dict[str, str] = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "menu": "alt",
    "option": "alt",
    "mod1": "alt",
    "cmd": "meta",
    "command": "meta",
    "meta": "meta",
    "super": "meta",
    "win": "meta",
    "windows": "meta",
    "mod4": "meta",
}

KEY_ALIASES: dict[str, str] = {
    "return": "enter",
    "enter": "enter",
    "tab": "tab",
    "escape": "escape",
    "esc": "escape",
    "space": "space",
    "backspace": "backspace",
    "delete": "delete",
    "del": "delete",
    "insert": "insert",
    "ins": "insert",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pgup": "pageup",
    "pagedown": "pagedown",
    "pgdn": "pagedown",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "capslock": "capslock",
    "numlock": "numlock",
}

for i in range(1, 13):
    KEY_ALIASES[f"f{i}"] = f"f{i}"


def modifier_alias(value: str, platform: str | None = None) -> str | None:
    plat = platform or sys.platform
    normalized = MODIFIER_ALIASES.get(value.lower())
    if plat == "darwin" and normalized == "meta":
        return "cmd"
    return normalized


def normalize_modifiers(value: str | None, platform: str | None = None) -> list[str]:
    if not value or not value.strip():
        return []
    plat = platform or sys.platform
    result: list[str] = []
    for part in value.split("+"):
        raw = part.strip()
        mod = modifier_alias(raw, plat)
        if not mod:
            raise ValueError(f"COMPUTER_UNSUPPORTED_KEY: unknown modifier {raw!r}")
        result.append(mod)
    return result


def normalize_key(value: str, platform: str | None = None) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("COMPUTER_UNSUPPORTED_KEY: key chord contains an empty key")
    plat = platform or sys.platform
    lowered = raw.lower()
    named = modifier_alias(lowered, plat) or KEY_ALIASES.get(lowered)
    if named:
        return named
    if len(raw) == 1 and raw.isalpha():
        return lowered
    if len(raw) == 1:
        raise ValueError(
            f"COMPUTER_UNSUPPORTED_KEY: single-character key {raw!r} loses layout shift state; use type action instead"
        )
    return lowered
