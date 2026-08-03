"""jarvis.shared.text.assistant_visible_text — focused minimal assistant text projection.

OpenClaw parity: mirrors
``openclaw-main/src/shared/text/assistant-visible-text.ts`` (33K).

This is a focused minimal port: it composes the surrounding text helpers
(``strip_reasoning_tags_from_text``, ``strip_final_tags``, etc.) and
exposes a single ``extract_assistant_visible_text`` function. Callers
needing the full parser-driven surface should provide their own IR
annotations and a custom caller-supplied stripper.
"""
from __future__ import annotations

from typing import Callable, Optional

from .final_tags import strip_final_tags
from .formatted_reasoning_message import strip_formatted_reasoning_message
from .reasoning_tags import strip_reasoning_tags_from_text


def extract_assistant_visible_text(
    text: str,
    *,
    stripper: Optional[Callable[[str], str]] = None,
) -> str:
    """Extract assistant-visible plain text from a possibly-tagged payload.

    Mirrors :func:`extractAssistantVisibleText`
    (``shared/text/assistant-visible-text.ts``).
    """
    if not isinstance(text, str):
        return ""
    if stripper is not None:
        return stripper(text)
    out = strip_reasoning_tags_from_text(text)
    out = strip_formatted_reasoning_message(out)
    out = strip_final_tags(out)
    return out.strip()


__all__ = ["extract_assistant_visible_text"]
