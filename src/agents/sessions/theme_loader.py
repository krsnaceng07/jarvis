"""jarvis.agents.sessions.theme_loader — theme loader.

OpenClaw parity: mirrors
``openclaw-main/src/agents/modes/interactive/theme/theme.ts``.

Public surface (matches the OpenClaw source):

- :class:`Theme` — a single loaded theme
  (JSON file with a ``name`` + color
  definitions).
- :func:`loadThemeFromPath` — parse a
  theme file from disk.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, TypedDict, cast


def _empty_theme_mapping() -> dict[str, object]:
    return {}


class ThemeSourceInfo(TypedDict, total=False):
    """Where a theme came from. Mirrors the
    ``sourceInfo`` field on :class:`Theme`."""

    path: str
    source: str
    scope: str
    origin: str
    baseDir: Optional[str]


@dataclass
class Theme:
    """A single loaded theme. Mirrors
    ``Theme`` (``theme.ts``).

    Attributes
    ----------
    name : str | None
        Theme name (from the JSON's
        ``name`` field).
    description : str | None
        Optional human-readable description.
    source_path : str | None
        Filesystem path of the theme file.
    file_path : str | None
        Alias for the theme file path used by
        the session resource tests and loaders.
    colors : dict
        Color palette (foreground /
        background / accent / etc.).
    styles : dict
        Per-style overrides (syntax
        highlighting, status line, etc.).
    source_info : ThemeSourceInfo | None
        Provenance info; populated by the
        resource loader.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    source_path: Optional[str] = None
    file_path: Optional[str] = None
    colors: dict[str, object] = field(default_factory=_empty_theme_mapping)
    styles: dict[str, object] = field(default_factory=_empty_theme_mapping)
    source_info: Optional[ThemeSourceInfo] = None


def loadThemeFromPath(file_path: str) -> Theme:
    """Load a single theme from a JSON file
    on disk. Mirrors ``loadThemeFromPath``
    (``theme.ts``).

    The parser is intentionally small and
    dependency-free: it reads the JSON object,
    preserves the color palette, and applies
    reasonable defaults for missing fields.
    """
    with open(file_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("theme file must contain a JSON object")

    payload = cast(dict[str, object], payload)
    name = payload.get("name", "")
    description = payload.get("description", "")
    colors_raw: object = payload.get("colors", {})
    styles_raw: object = payload.get("styles", {})

    if not isinstance(colors_raw, dict):
        raise ValueError("theme 'colors' must be an object")
    if not isinstance(styles_raw, dict):
        raise ValueError("theme 'styles' must be an object")

    colors_raw_dict = cast(dict[object, object], colors_raw)
    styles_raw_dict = cast(dict[object, object], styles_raw)
    colors: dict[str, object] = {}
    styles: dict[str, object] = {}
    for raw_key, raw_value in colors_raw_dict.items():
        colors[str(raw_key)] = raw_value
    for raw_key, raw_value in styles_raw_dict.items():
        styles[str(raw_key)] = raw_value

    return Theme(
        name=name if isinstance(name, str) else "",
        description=description if isinstance(description, str) else "",
        source_path=file_path,
        file_path=file_path,
        colors=colors,
        styles=styles,
        source_info=None,
    )


__all__ = [
    "Theme",
    "ThemeSourceInfo",
    "loadThemeFromPath",
]
