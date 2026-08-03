"""jarvis.shared.chat_content — chat-content text coercion.

OpenClaw parity: mirrors ``openclaw-main/src/shared/chat-content.ts``.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional


def coerce_chat_content_text(value: Any) -> str:
    """Coerce arbitrary provider content values into displayable text.

    Mirrors :func:`coerceChatContentText` (``shared/chat-content.ts``).
    """
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            return ""
    return ""


def extract_text_from_chat_content(
    content: Any,
    *,
    sanitize_text: Optional[Callable[[str], str]] = None,
    join_with: str = " ",
    normalize_text: Optional[Callable[[str], str]] = None,
) -> Optional[str]:
    """Extract normalized plain text from string content or text blocks.

    Mirrors :func:`extractTextFromChatContent` (``shared/chat-content.ts``).
    """
    if normalize_text is None:
        def _normalize(text: str) -> str:
            return " ".join(text.split()).strip()
        normalize_text = _normalize

    def sanitize(text: Any) -> str:
        raw = coerce_chat_content_text(text)
        sanitized = sanitize_text(raw) if sanitize_text else raw
        return coerce_chat_content_text(sanitized)

    def normalize(text: Any) -> str:
        return coerce_chat_content_text(normalize_text(coerce_chat_content_text(text)))

    if isinstance(content, str):
        value = sanitize(content)
        normalized = normalize(value)
        return normalized or None

    if not isinstance(content, list):
        return None

    chunks: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        # Non-text blocks (media, tool payloads) are skipped; we only want visible text.
        if block.get("type") != "text":
            continue
        text = block.get("text")
        value = sanitize(text)
        if value.strip():
            chunks.append(value)

    joined = normalize(join_with.join(chunks))
    return joined or None


__all__ = [
    "coerce_chat_content_text",
    "extract_text_from_chat_content",
]
