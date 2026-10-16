"""Channel plugin contracts and adapter protocols for JARVIS extensions.

Mirrors OpenClaw's ``src/plugin-sdk/channel-contract.ts`` and
``src/channels/plugins/types.plugin.ts``.

Channel plugins implement transport-specific adapters only. Core owns the
inbound 5-stage turn pipeline, mention gating, command gating, status reactions,
typing keepalives, and delivery orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from .channel_actions import (
    ApprovalAction,
    ChannelAction,
    ChannelActionKind,
    CommandAction,
    SelectAction,
    TextAction,
    UrlAction,
)
from .channel_adapters import (
    ChannelConversationBindings,
    ChannelOutboundAdapter,
    ChannelPairingAdapter,
    ChannelSecurityAdapter,
    ChannelThreadingAdapter,
)
from .channel_capabilities import (
    ChannelCapabilities,
    ChannelTtsVoiceDeliveryCapabilities,
)
from .contract import ChannelPlugin


@runtime_checkable
class StatusReactionAdapter(Protocol):
    """Protocol for channel plugins supporting message status reaction updates."""

    async def set_reaction(self, emoji: str) -> None:
        """Set or replace the current status reaction emoji."""
        ...

    async def clear_reaction(self) -> None:
        """Clear all status reactions (for single-slot platforms)."""
        ...

    async def remove_reaction(self, emoji: str) -> None:
        """Remove a specific reaction emoji."""
        ...


@runtime_checkable
class ChannelMessageAdapter(Protocol):
    """Universal message adapter protocol for LLM message tool interactions."""

    async def send_text(
        self,
        conversation_id: str,
        text: str,
        reply_to_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Send a plain text message."""
        ...

    async def edit_message(
        self,
        conversation_id: str,
        message_id: str,
        text: str,
    ) -> Any:
        """Edit a previously sent message."""
        ...

    async def delete_message(
        self,
        conversation_id: str,
        message_id: str,
    ) -> bool:
        """Delete a message."""
        ...

    async def react(
        self,
        conversation_id: str,
        message_id: str,
        emoji: str,
    ) -> bool:
        """React to a message with an emoji."""
        ...


@dataclass(frozen=True, slots=True)
class TypingCallbacks:
    """Typing indicator callbacks exposed to channel turn dispatchers."""

    on_reply_start: Callable[[], Awaitable[None]]
    on_idle: Callable[[], None] | None = None
    on_cleanup: Callable[[], None] | None = None


__all__ = [
    # Plugin & Capabilities
    "ChannelPlugin",
    "ChannelCapabilities",
    "ChannelTtsVoiceDeliveryCapabilities",
    # Adapters
    "ChannelSecurityAdapter",
    "ChannelPairingAdapter",
    "ChannelThreadingAdapter",
    "ChannelOutboundAdapter",
    "ChannelConversationBindings",
    "ChannelMessageAdapter",
    "StatusReactionAdapter",
    "TypingCallbacks",
    # Presentation Actions
    "ChannelAction",
    "ChannelActionKind",
    "TextAction",
    "CommandAction",
    "ApprovalAction",
    "UrlAction",
    "SelectAction",
]
