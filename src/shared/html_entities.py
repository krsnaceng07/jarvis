"""jarvis.shared.html_entities — HTML5 entity decoder.

OpenClaw parity: mirrors ``openclaw-main/src/shared/html-entities.ts``.
"""
from __future__ import annotations

import html
import re

#: Match semicolon-terminated named/numeric HTML entities.
_HTML_ENTITY_RE = re.compile(
    r"&(?:#x([0-9a-f]+)|#(\d+)|([a-z][a-z0-9]+));",
    re.IGNORECASE,
)

#: Mixed-case XML legacy entity names that need lowercase fallback.
_LEGACY_CASE_INSENSITIVE_ENTITY_NAME_RE = re.compile(r"^(?:amp|quot|apos|lt|gt)$", re.IGNORECASE)

#: HTML named entity table (subset mirrored from Python's stdlib).
_NAMED_ENTITIES = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
    "nbsp": "\u00a0",
}


def _is_unicode_scalar(code_point: int) -> bool:
    return (
        isinstance(code_point, int)
        and 0 <= code_point <= 0x10FFFF
        and not (0xD800 <= code_point <= 0xDFFF)
    )


def _decode_named(entity: str) -> str:
    """Decode a named HTML entity, falling back to lowercase for legacy mixed-case."""
    decoded = html.unescape(entity)
    if decoded != entity:
        return decoded
    name = entity[1:-1]
    if _LEGACY_CASE_INSENSITIVE_ENTITY_NAME_RE.match(name):
        return html.unescape(entity.lower())
    return _NAMED_ENTITIES.get(name.lower(), entity)


def decode_html_entities(html_text: str) -> str:
    """Decode semicolon-terminated HTML5 named and numeric entities exactly once.

    Mirrors :func:`decodeHtmlEntities` (``shared/html-entities.ts``).
    """
    if not isinstance(html_text, str) or "&" not in html_text:
        return html_text

    def _replace(match: "re.Match[str]") -> str:
        entity = match.group(0)
        hex_part = match.group(1)
        decimal_part = match.group(2)
        name_part = match.group(3)
        if hex_part is None and decimal_part is None:
            return _decode_named(entity)
        try:
            code_point = int(hex_part, 16) if hex_part is not None else int(decimal_part, 10)
        except ValueError:
            return entity
        if _is_unicode_scalar(code_point):
            return chr(code_point)
        return entity

    # Decode only references present in the original input so decoded ampersands
    # cannot trigger a second pass.
    return _HTML_ENTITY_RE.sub(_replace, html_text)


__all__ = ["decode_html_entities"]
