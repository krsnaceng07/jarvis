"""jarvis.utils.message_channel_constants — internal channel id constants.

OpenClaw parity: mirrors
``openclaw-main/src/utils/message-channel-constants.ts``.

Public surface:

- :data:`INTERNAL_MESSAGE_CHANNEL`
- :data:`INTERNAL_NON_DELIVERY_CHANNELS`
- :func:`internal_session_conversation_id`
- :func:`is_internal_non_delivery_channel`
"""
from __future__ import annotations

from typing import Iterable, Optional, Set, Union


#: Internal channel id used for the webchat/session-only surface.
INTERNAL_MESSAGE_CHANNEL = "webchat"

#: Internal, non-delivery source channels (heartbeat, cron, webhook, etc.).
INTERNAL_NON_DELIVERY_CHANNELS = ("heartbeat", "cron", "webhook", "voice", "sessions_send")


def _is_string_option(value: object, options: Union[Iterable[str], Set[str]]) -> bool:
    return isinstance(value, str) and value in options


def internal_session_conversation_id(
    channel_id: str,
    session_key: Optional[str],
) -> Optional[str]:
    """Return the session key only when ``channel_id`` is the internal webchat channel.

    Mirrors :func:`internalSessionConversationId`
    (``utils/message-channel-constants.ts``).
    """
    if channel_id == INTERNAL_MESSAGE_CHANNEL:
        return session_key
    return None


def is_internal_non_delivery_channel(value: object) -> bool:
    """Return whether ``value`` is one of the internal, non-delivery source channels.

    Mirrors :func:`isInternalNonDeliveryChannel`
    (``utils/message-channel-constants.ts``).
    """
    return _is_string_option(value, INTERNAL_NON_DELIVERY_CHANNELS)


__all__ = [
    "INTERNAL_MESSAGE_CHANNEL",
    "INTERNAL_NON_DELIVERY_CHANNELS",
    "internal_session_conversation_id",
    "is_internal_non_delivery_channel",
]
