"""jarvis.agents.sessions.tools.render_utils — rendering helpers for session tool output.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/render-utils.ts``.

Phase 6.10b — TUI rendering helpers.

The OpenClaw source's helpers are deeply
coupled to the TUI ``Theme`` type
(``@earendil-works/pi-tui``) and the
``imageFallback`` / ``getImageDimensions``
helpers. The Python port ships the
TUI-independent helpers now and defers the
TUI-coupled ones to Phase 6.12+ (the actual
TUI lands then).

Adaptations
-----------
- The OpenClaw source's ``Theme.fg(tag, text)``
  becomes a no-op (the Python port returns
  the text unchanged). The full TUI tagging
  lands in Phase 6.12 with the TUI module.
- The OpenClaw source's ``sanitizeBinaryOutput``
  (a shell-utils helper) is replaced with a
  simple ``\\r`` strip (the full sanitizer
  lands in Phase 6.10+ with the bash tool).
- The OpenClaw source's
  ``keyHint(action, label)`` becomes a plain
  string — the keybinding hint UI lands in
  Phase 6.12.
- The OpenClaw source's
  ``getCapabilities()`` + ``imageFallback``
  helpers are dropped (TUI-coupled; the
  image-fallback markers are deferred).
"""
from __future__ import annotations

import os
from typing import Any, Iterable, Optional

from .truncate import DEFAULT_MAX_BYTES, TruncationResult, format_size


# ============================================================================
# TUI-independent helpers
# ============================================================================


def shorten_path(path: Any) -> str:
    """Shorten a path under the current home
    directory. Mirrors ``shortenPath``
    (``render-utils.ts:14-27``)."""
    if not isinstance(path, str):
        return ""
    home = os.path.expanduser("~")
    if path == home:
        return "~"
    if path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def str_(value: Any) -> Optional[str]:
    """Return ``value`` if it's a ``str``,
    ``""`` for ``None``, ``None`` for other
    types. Mirrors ``str``
    (``render-utils.ts:29-38``).

    The trailing underscore avoids clashing
    with the builtin :class:`str`.
    """
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return None


def replace_tabs(text: str) -> str:
    """Replace tabs with 3 spaces. Mirrors
    ``replaceTabs`` (``render-utils.ts:40-43``)."""
    return text.replace("\t", "   ")


def normalize_display_text(text: str) -> str:
    """Strip ``\\r`` from terminal output.
    Mirrors ``normalizeDisplayText``
    (``render-utils.ts:45-48``)."""
    return text.replace("\r", "")


# ============================================================================
# TUI-coupled helpers (Phase 6.12 lands the real Theme)
# ============================================================================


def get_text_output(
    result: Optional[dict],
    show_images: bool = True,
) -> str:
    """Extract text output (plus optional image
    fallback markers) from a tool result.
    Mirrors ``getTextOutput``
    (``render-utils.ts:51-85``).

    The Python port returns plain text (no
    TUI styling). Image blocks are ignored
    in the Phase 6.10b port; the TUI lands
    in Phase 6.12 and ``imageFallback`` then
    returns the canonical "[image omitted]"
    marker.
    """
    if not result:
        return ""
    content = result.get("content") or []
    text_blocks = [c for c in content if c.get("type") == "text"]
    return "\n".join(
        (c.get("text") or "").replace("\r", "") for c in text_blocks
    )


def format_session_tool_output(
    result: dict,
    options: dict,
    show_images: bool = True,
    collapsed_line_limit: int = 20,
) -> str:
    """Render a tool result's text output
    with a collapsed-line hint. Mirrors
    ``formatSessionToolOutput``
    (``render-utils.ts:87-109``).

    The Python port returns plain text
    (the TUI ``theme.fg`` styling lands
    in Phase 6.12). The keybinding hint is
    the literal string ``"<keyhint:app.tools.expand>"``
    so TUI integration can replace it.
    """
    output = get_text_output(result, show_images).strip()
    if not output:
        return ""
    lines = output.split("\n")
    expanded = bool(options.get("expanded"))
    max_lines = len(lines) if expanded else collapsed_line_limit
    display_lines = lines[:max_lines]
    remaining = len(lines) - max_lines
    text = "\n" + "\n".join(display_lines)
    if remaining > 0:
        text += (
            f"\n... ({remaining} more lines, "
            f"<keyhint:app.tools.expand> to expand)"
        )
    return text


def append_session_tool_truncation_warning(
    text: str,
    options: Optional[dict] = None,
) -> str:
    """Append a truncation warning to ``text``.
    Mirrors ``appendSessionToolTruncationWarning``
    (``render-utils.ts:111-132``)."""
    options = options or {}
    warnings: list[str] = []
    limit = options.get("limit")
    if isinstance(limit, dict) and "count" in limit and "noun" in limit:
        warnings.append(f"{limit['count']} {limit['noun']} limit")
    truncation = options.get("truncation")
    if isinstance(truncation, dict) and truncation.get("truncated"):
        max_bytes = truncation.get("maxBytes", DEFAULT_MAX_BYTES)
        warnings.append(f"{format_size(max_bytes)} limit")
    for w in options.get("additionalWarnings") or []:
        warnings.append(w)
    if not warnings:
        return text
    return f"{text}\n[Truncated: {', '.join(warnings)}]"


def invalid_arg_text() -> str:
    """Return the invalid-argument marker
    (plain text; TUI styling lands in
    Phase 6.12). Mirrors ``invalidArgText``
    (``render-utils.ts:134-137``)."""
    return "[invalid arg]"


__all__ = [
    "append_session_tool_truncation_warning",
    "format_session_tool_output",
    "get_text_output",
    "invalid_arg_text",
    "normalize_display_text",
    "replace_tabs",
    "shorten_path",
    "str_",
]
