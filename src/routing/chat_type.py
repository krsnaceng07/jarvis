"""jarvis.routing.chat_type — canonical chat-type normalization.

OpenClaw parity: mirrors ``src/channels/chat-type.ts``.
(Placed under routing/ because JARVIS has no src/channels/ package yet;
the routing modules are the only consumers in Phase 5.13.)
"""

from __future__ import annotations

from jarvis_normalization_core.string_coerce import normalize_optional_lowercase_string

# ChatType = "direct" | "group" | "channel"


def normalize_chat_type(value: object) -> str | None:
    """Normalize a raw chat-type string to ``direct``/``group``/``channel``.

    Mirrors ``normalizeChatType``: ``"dm"`` folds into ``"direct"``;
    unknown values return ``None``.
    """
    normalized = normalize_optional_lowercase_string(value)
    if normalized in ("direct", "dm"):
        return "direct"
    if normalized == "group":
        return "group"
    if normalized == "channel":
        return "channel"
    return None


__all__ = ["normalize_chat_type"]
