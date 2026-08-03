"""jarvis.utils.conversation_target — conversation target normalization.

OpenClaw parity: mirrors ``openclaw-main/src/utils/conversation-target.ts``.

Public surface:

- :func:`normalize_conversation_target_params`
- :class:`ConversationTargetParams`
"""
from __future__ import annotations

from typing import Any, Optional, Union


class ConversationTargetParams:
    """Typed view of conversation target inputs."""

    def __init__(
        self,
        channel: Optional[str] = None,
        conversation_id: Optional[Union[str, int]] = None,
        parent_conversation_id: Optional[Union[str, int]] = None,
    ) -> None:
        self.channel = channel
        self.conversation_id = conversation_id
        self.parent_conversation_id = parent_conversation_id


def _normalize_conversation_id(value: Any) -> Optional[str]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value is not None and value == value:
        return str(int(value))
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def normalize_conversation_target_params(
    params: ConversationTargetParams,
) -> dict:
    """Normalize a :class:`ConversationTargetParams` to canonical fields.

    Mirrors :func:`normalizeConversationTargetParams` (``utils/conversation-target.ts``).
    """
    if isinstance(params, dict):
        params = ConversationTargetParams(
            channel=params.get("channel"),
            conversation_id=params.get("conversationId") or params.get("conversation_id"),
            parent_conversation_id=params.get("parentConversationId")
            or params.get("parent_conversation_id"),
        )
    channel = None
    if isinstance(params.channel, str):
        cleaned = params.channel.strip()
        channel = cleaned.lower() or None
    conversation_id = _normalize_conversation_id(params.conversation_id)
    parent_conversation_id = _normalize_conversation_id(params.parent_conversation_id)
    return {
        "channel": channel,
        "conversationId": conversation_id,
        "parentConversationId": parent_conversation_id,
    }


__all__ = [
    "ConversationTargetParams",
    "normalize_conversation_target_params",
]
