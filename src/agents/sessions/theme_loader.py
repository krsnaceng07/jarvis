"""jarvis.agents.sessions.theme_loader — theme loader (stub).

OpenClaw parity: mirrors
``openclaw-main/src/agents/modes/interactive/theme/theme.ts``.

Public surface (matches the OpenClaw source):

- :class:`Theme` — a single loaded theme
  (JSON file with a ``name`` + color
  definitions).
- :func:`loadThemeFromPath` — parse a
  theme file from disk.

Phase 6.11b — STUB. ``loadThemeFromPath``
raises ``NotImplementedError`` for now;
the full JSON parsing lands in Phase 6.12+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypedDict


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
    source_path : str | None
        Filesystem path of the theme file.
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
    source_path: Optional[str] = None
    colors: dict = field(default_factory=dict)
    styles: dict = field(default_factory=dict)
    source_info: Optional[ThemeSourceInfo] = None


def loadThemeFromPath(file_path: str) -> Theme:
    """Load a single theme from a JSON file
    on disk. Mirrors ``loadThemeFromPath``
    (``theme.ts``).

    Phase 6.11b — STUB. Raises
    :class:`NotImplementedError`; the full
    JSON parser lands in Phase 6.12+.
    """
    raise NotImplementedError(
        "loadThemeFromPath is a Phase 6.11b stub — "
        "the full theme JSON parser lands in Phase 6.12+."
    )


__all__ = [
    "Theme",
    "ThemeSourceInfo",
    "loadThemeFromPath",
]
