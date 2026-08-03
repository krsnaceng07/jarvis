"""jarvis.utils.message_channel_core — message channel normalization core.

OpenClaw parity: mirrors
``openclaw-main/src/utils/message-channel-core.ts``.

Public surface:

- :func:`normalize_message_channel`
- :func:`is_deliverable_message_channel`
"""
from __future__ import annotations

from typing import Any, List, Optional

from .message_channel_constants import INTERNAL_MESSAGE_CHANNEL


# Built-in channel aliases (subset of OpenClaw's CHANNEL_IDS).
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


def _normalize_optional_lowercase_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        return cleaned or None
    return None


def _normalize_chat_channel_id(value: str) -> Optional[str]:
    """Subset of OpenClaw's ``normalizeChatChannelId`` (plugin-owned aliases deferred)."""
    if value in _BUILTIN_CHANNELS:
        return value
    return None


def _normalize_any_channel_id(value: str) -> Optional[str]:
    """Subset of OpenClaw's ``normalizeAnyChannelId`` (plugin registry deferred)."""
    return value or None


def normalize_message_channel(raw: Any = None) -> Optional[str]:
    """Normalize raw channel names, aliases, and internal webchat into canonical ids.

    Mirrors :func:`normalizeMessageChannel` (``utils/message-channel-core.ts``).
    """
    normalized = _normalize_optional_lowercase_string(raw)
    if not normalized:
        return None
    if normalized == INTERNAL_MESSAGE_CHANNEL:
        return INTERNAL_MESSAGE_CHANNEL
    built_in = _normalize_chat_channel_id(normalized)
    if built_in:
        return built_in
    return _normalize_any_channel_id(normalized) or normalized


def is_deliverable_message_channel(value: Any) -> bool:
    """Return true when ``value`` is a normalized, non-internal delivery channel id.

    Mirrors :func:`isDeliverableMessageChannel` (``utils/message-channel-core.ts``).
    """
    if not isinstance(value, str):
        return False
    normalized = normalize_message_channel(value)
    return (
        normalized is not None
        and normalized != INTERNAL_MESSAGE_CHANNEL
        and normalized == value
    )


__all__ = [
    "normalize_message_channel",
    "is_deliverable_message_channel",
]
