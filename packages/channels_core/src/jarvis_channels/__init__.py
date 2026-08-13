"""jarvis_channels — JARVIS channel transport contracts.

Mirrors OpenClaw's ``src/channels/`` subsystem. Provides the typed
shapes for inbound/outbound messages, channel sessions, the channel
router that maps incoming events to the right plugin, allowlist policy,
presence (typing indicators), reply formatting, and session bindings.

Wave 1: full W1 surface is now available.

Importing this package is the canonical way for plugins and the
gateway to work with channel data — they should not import from
``src.channels`` directly.
"""

from __future__ import annotations

from .allowlist import (
    ALLOW_ALL,
    AllowlistPolicy,
    is_allowed,
    normalize_allowlist,
)
from .bindings import (
    BindingRegistry,
    derive_session_key,
    derive_webhook_path,
    session_from_message,
)
from .presence import PresenceEmitter, ReactionEmitter
from .reply import (
    channel_limit,
    format_reply,
    sender_label,
    split_reply,
    strip_markdown,
)
from .routing import ChannelRouter, ChannelTarget
from .types import ChannelSession, InboundMessage, OutboundMessage

__all__ = [
    # Types
    "InboundMessage",
    "OutboundMessage",
    "ChannelSession",
    # Routing
    "ChannelTarget",
    "ChannelRouter",
    # Allowlist
    "ALLOW_ALL",
    "AllowlistPolicy",
    "is_allowed",
    "normalize_allowlist",
    # Bindings
    "BindingRegistry",
    "derive_session_key",
    "derive_webhook_path",
    "session_from_message",
    # Presence
    "PresenceEmitter",
    "ReactionEmitter",
    # Reply
    "channel_limit",
    "format_reply",
    "split_reply",
    "sender_label",
    "strip_markdown",
]
