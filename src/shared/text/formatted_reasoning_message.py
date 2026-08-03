"""jarvis.shared.text.formatted_reasoning_message — strip Reasoning preambles.

OpenClaw parity: mirrors
``openclaw-main/src/shared/text/formatted-reasoning-message.ts``.
"""
from __future__ import annotations

import re

from .reasoning_tags import strip_reasoning_tags_from_text


def strip_formatted_reasoning_message(text: str) -> str:
    """Strip provider-formatted Reasoning/Thinking preambles from visible text.

    Mirrors :func:`stripFormattedReasoningMessage`
    (``shared/text/formatted-reasoning-message.ts``).
    """
    if not isinstance(text, str):
        return text
    stripped = strip_reasoning_tags_from_text(text)
    lines = re.split(r"\r?\n", stripped)
    prefix = (lines[0] or "").strip() if lines else ""
    if prefix != "Reasoning:" and not re.match(r"^Thinking\.{0,3}$", prefix or ""):
        return stripped
    if re.match(r"^Thinking\.{0,3}$", prefix or ""):
        first_body = next((l for l in lines[1:] if l.strip()), "")
        trimmed = first_body.strip()
        if not trimmed or not (
            trimmed.startswith("_") and trimmed.endswith("_") and len(trimmed) >= 2
        ):
            return stripped
    # Drop blank/italic summary preamble lines but preserve the substantive
    # answer body exactly after the first non-preamble line.
    index = 1
    while index < len(lines):
        trimmed = (lines[index] or "").strip()
        if not trimmed or (trimmed.startswith("_") and trimmed.endswith("_") and len(trimmed) >= 2):
            index += 1
            continue
        break
    return "\n".join(lines[index:]).strip()


__all__ = ["strip_formatted_reasoning_message"]
