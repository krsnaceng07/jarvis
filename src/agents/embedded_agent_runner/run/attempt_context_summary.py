"""jarvis.agents.embedded_agent_runner.run.attempt_context_summary — summarize session context + snapshot recent messages.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-context-summary.ts``.

Public surface:

Constants:

- :data:`MAX_BTW_SNAPSHOT_MESSAGES`

Functions:

- :func:`summarize_session_context`
- :func:`snapshot_recent_messages`

Phase 7.6d-1 — focused minimal port.

The OpenClaw source is small (~2K) and pure. The Python port keeps
the public surface and ports the small pure helpers inline.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


#: Maximum number of messages retained in a recent snapshot.
#: Mirrors :data:`MAX_BTW_SNAPSHOT_MESSAGES`
#: (``attempt-context-summary.ts:3``).
MAX_BTW_SNAPSHOT_MESSAGES: int = 100


#: Session-context summary shape.
SessionContextSummary = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers (ported as-is)
# ---------------------------------------------------------------------------


def _summarize_message_payload(
    msg: Any,
) -> Dict[str, int]:
    """Return ``{textChars, imageBlocks}`` for one message.

    Mirrors :func:`summarizeMessagePayload`
    (``attempt-context-summary.ts:5-31``).
    """
    if not isinstance(msg, dict):
        return {"textChars": 0, "imageBlocks": 0}
    content = msg.get("content")
    if isinstance(content, str):
        return {"textChars": len(content), "imageBlocks": 0}
    if not isinstance(content, list):
        return {"textChars": 0, "imageBlocks": 0}
    text_chars = 0
    image_blocks = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "image":
            image_blocks += 1
            continue
        text = block.get("text")
        if isinstance(text, str):
            text_chars += len(text)
    return {"textChars": text_chars, "imageBlocks": image_blocks}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def summarize_session_context(
    messages: List[Any],
) -> SessionContextSummary:
    """Summarize a session-context message list.

    Mirrors :func:`summarizeSessionContext`
    (``attempt-context-summary.ts:33-66``).
    """
    if not isinstance(messages, list):
        messages = []
    role_counts: Dict[str, int] = {}
    total_text_chars = 0
    total_image_blocks = 0
    max_message_text_chars = 0
    for msg in messages:
        role = msg.get("role") if isinstance(msg, dict) else None
        role_key = role if isinstance(role, str) else "unknown"
        role_counts[role_key] = role_counts.get(role_key, 0) + 1
        payload = _summarize_message_payload(msg)
        total_text_chars += payload["textChars"]
        total_image_blocks += payload["imageBlocks"]
        if payload["textChars"] > max_message_text_chars:
            max_message_text_chars = payload["textChars"]
    sorted_counts = sorted(role_counts.items(), key=lambda kv: kv[0])
    role_counts_str = ",".join(
        f"{role}:{count}" for role, count in sorted_counts
    ) or "none"
    return {
        "roleCounts": role_counts_str,
        "totalTextChars": total_text_chars,
        "totalImageBlocks": total_image_blocks,
        "maxMessageTextChars": max_message_text_chars,
    }


def snapshot_recent_messages(
    messages: List[Any],
) -> List[Any]:
    """Return the most-recent :data:`MAX_BTW_SNAPSHOT_MESSAGES` messages.

    Mirrors :func:`snapshotRecentMessages`
    (``attempt-context-summary.ts:68-70``).
    """
    if not isinstance(messages, list):
        return []
    return list(messages[-MAX_BTW_SNAPSHOT_MESSAGES:])


__all__ = [
    "MAX_BTW_SNAPSHOT_MESSAGES",
    "SessionContextSummary",
    "snapshot_recent_messages",
    "summarize_session_context",
]
