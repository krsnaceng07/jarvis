"""jarvis.agents.embedded_agent_runner.run.history_image_prune — prune image blocks from history messages.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/history-image-prune.ts``.

Public surface:

- :func:`prune_history_images`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List


#: Agent message shape.
AgentMessage = Dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers (ported as-is)
# ---------------------------------------------------------------------------


def _strip_images_from_message(message: AgentMessage) -> AgentMessage:
    """Return a deep-copy of ``message`` with image blocks stripped.

    Mirrors the inline OpenClaw source helper.
    """
    if not isinstance(message, dict):
        return message
    cloned = copy.deepcopy(message)
    content = cloned.get("content")
    if isinstance(content, list):
        cloned["content"] = [
            block
            for block in content
            if not (
                isinstance(block, dict)
                and (block.get("type") or block.get("kind")) == "image"
            )
        ]
    return cloned


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prune_history_images(
    messages: List[Any],
) -> List[AgentMessage]:
    """Prune image blocks from the history messages.

    Mirrors :func:`pruneHistoryImages` (``history-image-prune.ts``).
    """
    if not isinstance(messages, list):
        return []
    return [_strip_images_from_message(message) for message in messages]


__all__ = [
    "AgentMessage",
    "prune_history_images",
]
