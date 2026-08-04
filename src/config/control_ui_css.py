"""jarvis.config.control_ui_css — Control UI CSS width normalizer and validator.

OpenClaw parity: mirrors ``openclaw-main/src/config/control-ui-css.ts``.
"""
from __future__ import annotations

import re
from typing import Set


CSS_WIDTH_KEYWORDS: Set[str] = {"none", "min-content", "max-content"}
CSS_WIDTH_FUNCTIONS: Set[str] = {"calc", "clamp", "fit-content", "max", "min"}
CSS_WIDTH_UNITS: Set[str] = {"ch", "em", "rem", "vh", "vmax", "vmin", "vw", "px"}
CSS_WIDTH_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z.%+\-*/(),\s]+$")
CSS_WIDTH_IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
CSS_WIDTH_SIMPLE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)?|\.\d+)(?:px|rem|em|ch|vw|vh|vmin|vmax|%)$",
    re.IGNORECASE,
)
CSS_WIDTH_MAX_LENGTH = 96


def _has_balanced_parentheses(value: str) -> bool:
    depth = 0
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _has_allowed_identifiers(value: str) -> bool:
    for match in CSS_WIDTH_IDENTIFIER_RE.finditer(value):
        ident = match.group(0).lower()
        if (
            ident not in CSS_WIDTH_FUNCTIONS
            and ident not in CSS_WIDTH_KEYWORDS
            and ident not in CSS_WIDTH_UNITS
        ):
            return False
    return True


def normalize_control_ui_chat_message_max_width(value: str) -> str:
    """Normalize operator-provided Control UI chat max-width CSS values.

    Mirrors :func:`normalizeControlUiChatMessageMaxWidth`
    (``shared/config/control-ui-css.ts``).
    """
    return re.sub(r"\s+", " ", value.strip())


def is_valid_control_ui_chat_message_max_width(value: str) -> bool:
    """Validate the constrained CSS width grammar.

    Mirrors :func:`isValidControlUiChatMessageMaxWidth`
    (``shared/config/control-ui-css.ts``).
    """
    normalized = normalize_control_ui_chat_message_max_width(value)
    if not normalized or len(normalized) > CSS_WIDTH_MAX_LENGTH:
        return False
    if normalized.lower() in CSS_WIDTH_KEYWORDS:
        return True
    if CSS_WIDTH_SIMPLE_RE.match(normalized):
        return True
    if not CSS_WIDTH_ALLOWED_CHARS.match(normalized):
        return False
    if not _has_balanced_parentheses(normalized) or not _has_allowed_identifiers(normalized):
        return False
    return bool(re.match(r"^(?:calc|clamp|fit-content|max|min)\(.+\)$", normalized, re.IGNORECASE))


__all__ = [
    "CSS_WIDTH_KEYWORDS",
    "CSS_WIDTH_FUNCTIONS",
    "CSS_WIDTH_UNITS",
    "CSS_WIDTH_MAX_LENGTH",
    "normalize_control_ui_chat_message_max_width",
    "is_valid_control_ui_chat_message_max_width",
]
