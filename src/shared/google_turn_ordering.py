"""jarvis.shared.google_turn_ordering — Google assistant-first sanitization.

OpenClaw parity: mirrors ``openclaw-main/src/shared/google-turn-ordering.ts``.
"""
from __future__ import annotations

from typing import Any, Dict, List

#: Synthetic user bootstrap marker for Google-style providers.
_GOOGLE_TURN_ORDER_BOOTSTRAP_TEXT = "(session bootstrap)"


def sanitize_google_assistant_first_ordering(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prepend a synthetic user bootstrap when the first turn is assistant.

    Google chat APIs reject assistant-first transcripts. The bootstrap marker
    makes the mutation idempotent while preserving the original assistant turn.

    Mirrors :func:`sanitizeGoogleAssistantFirstOrdering`
    (``shared/google-turn-ordering.ts``).
    """
    if not messages:
        return messages
    first = messages[0] or {}
    role = first.get("role")
    content = first.get("content")
    if (
        role == "user"
        and isinstance(content, str)
        and content.strip() == _GOOGLE_TURN_ORDER_BOOTSTRAP_TEXT
    ):
        return messages
    if role != "assistant":
        return messages
    bootstrap: Dict[str, Any] = {
        "role": "user",
        "content": _GOOGLE_TURN_ORDER_BOOTSTRAP_TEXT,
        "timestamp": _now_ms(),
    }
    return [bootstrap, *messages]


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


__all__ = ["sanitize_google_assistant_first_ordering"]
