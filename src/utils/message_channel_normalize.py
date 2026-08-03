"""jarvis.utils.message_channel_normalize — channel id + Gateway routing helpers.

OpenClaw parity: mirrors
``openclaw-main/src/utils/message-channel-normalize.ts``.

Public surface:

- :func:`normalize_message_channel`
- :func:`list_deliverable_message_channels`
- :func:`is_gateway_message_channel`
- :func:`is_deliverable_message_channel`
- :func:`resolve_gateway_message_channel`
- :func:`resolve_message_channel`
"""
from __future__ import annotations

from typing import List, Optional

from .message_channel_constants import INTERNAL_MESSAGE_CHANNEL
from .message_channel_core import (
    is_deliverable_message_channel as _core_is_deliverable,
    normalize_message_channel as _core_normalize,
)


def normalize_message_channel(raw: object = None) -> Optional[str]:
    """Public re-export of the core normalizer.

    Mirrors :func:`normalizeMessageChannel` (``utils/message-channel-normalize.ts``).
    """
    return _core_normalize(raw)


# Minimal built-in channel id set; plugin channels are loaded by the registry.
_BUILTIN_CHANNELS = (
    "telegram",
    "discord",
    "slack",
    "whatsapp",
    "signal",
    "imessage",
    "msteams",
    "matrix",
    "irc",
    "feishu",
    "line",
    "qqbot",
    "sms",
    "voice",
    "webchat",
    "tui",
)


def list_deliverable_message_channels() -> List[str]:
    """List built-in and registered plugin channel ids that can receive delivery.

    Mirrors :func:`listDeliverableMessageChannels`
    (``utils/message-channel-normalize.ts``).
    """
    return list(_BUILTIN_CHANNELS)


def is_gateway_message_channel(value: str) -> bool:
    """Return whether ``value`` is a valid Gateway message channel id.

    Mirrors :func:`isGatewayMessageChannel` (``utils/message-channel-normalize.ts``).
    """
    if not isinstance(value, str):
        return False
    return value in list_deliverable_message_channels() or value == INTERNAL_MESSAGE_CHANNEL


def is_deliverable_message_channel(value: str) -> bool:
    """Return whether ``value`` is a deliverable, non-internal channel id.

    Mirrors :func:`isDeliverableMessageChannel` (``utils/message-channel-normalize.ts``).
    """
    return _core_is_deliverable(value)


def resolve_gateway_message_channel(raw: object = None) -> Optional[str]:
    """Normalize and validate a raw channel value for Gateway routing.

    Mirrors :func:`resolveGatewayMessageChannel` (``utils/message-channel-normalize.ts``).
    """
    normalized = normalize_message_channel(raw)
    if not normalized:
        return None
    return normalized if is_gateway_message_channel(normalized) else None


def resolve_message_channel(
    primary: object = None,
    fallback: object = None,
) -> Optional[str]:
    """Normalize the primary channel or fall back to a secondary value.

    Mirrors :func:`resolveMessageChannel` (``utils/message-channel-normalize.ts``).
    """
    return normalize_message_channel(primary) or normalize_message_channel(fallback)


__all__ = [
    "normalize_message_channel",
    "list_deliverable_message_channels",
    "is_gateway_message_channel",
    "is_deliverable_message_channel",
    "resolve_gateway_message_channel",
    "resolve_message_channel",
]
