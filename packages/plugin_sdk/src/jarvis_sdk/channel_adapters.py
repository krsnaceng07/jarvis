"""Channel plugin adapter protocols.

Mirrors OpenClaw's per-adapter type definitions from
``src/plugins/types.core.ts`` and ``src/channels/plugins/types.ts``.

Each adapter covers a distinct concern:

- ``ChannelSecurityAdapter`` — DM policy, allowlist routing, audit findings.
- ``ChannelPairingAdapter``  — account pairing, allow-entry normalisation.
- ``ChannelThreadingAdapter`` — reply-to / threading mode resolution.
- ``ChannelOutboundAdapter`` — rendering outbound messages (text, media, poll).
- ``ChannelConversationBindings`` — conversation binding lifecycle.

Channels are **not** required to implement all adapters; the host treats
absent (``None``) adapters as transport-defaults / no-ops. Supply only the
adapters your transport actually needs.

Usage
-----
.. code-block:: python

    from jarvis_sdk.channel_adapters import (
        ChannelSecurityAdapter,
        ChannelOutboundAdapter,
    )
    from jarvis_sdk.plugin_entry import (
        create_chat_channel_plugin,
        define_channel_plugin_entry,
    )

    class MySecurityAdapter(ChannelSecurityAdapter):
        def resolve_dm_policy(self, ctx):
            return {"policy": "allowlist"}

    entry = define_channel_plugin_entry(
        id="my-channel",
        name="My Channel",
        description="...",
        register=lambda api: (
            api.register_channel(
                create_chat_channel_plugin(
                    id="my-channel",
                    security=MySecurityAdapter(),
                )
            )
            if api.registration_mode == "full" else None
        ),
    )
"""

from __future__ import annotations

from abc import ABC
from typing import Any


class ChannelSecurityAdapter(ABC):
    """Security policy adapter for a channel plugin.

    Mirrors OpenClaw's ``ChannelSecurityAdapter<TResolvedAccount>`` type.

    The host calls these methods to enforce DM policy and collect audit
    findings. Override only the methods your transport supports; defaults
    are no-op / permissive.
    """

    def resolve_dm_policy(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Return the DM routing policy for an inbound message context.

        ``ctx`` carries ``sender_id``, ``account``, and transport facts.
        Return ``{"policy": "allow"}`` to let the message through,
        ``{"policy": "deny", "reason": "..."}`` to reject, or
        ``{"policy": "allowlist"}`` to defer to the allowlist.
        """
        return {"policy": "allow"}

    def resolve_dm_routing(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """Return the routing target for an allowed DM.

        Maps a sender's resolved account to a JARVIS session target.
        Default returns ``ctx`` unchanged.
        """
        return ctx

    def collect_warnings(self, ctx: dict[str, Any]) -> list[str]:
        """Return human-readable security warnings for the dashboard.

        Called during ``jarvis doctor`` and the plugin management UI.
        """
        return []

    def collect_audit_findings(self, ctx: dict[str, Any]) -> list[dict[str, Any]]:
        """Return structured audit findings for the security audit pipeline.

        Each finding is a dict with at least ``{"severity": str, "message": str}``.
        """
        return []


class ChannelPairingAdapter(ABC):
    """Account pairing adapter for a channel plugin.

    Mirrors OpenClaw's ``ChannelPairingAdapter`` type. Handles the flow
    where a JARVIS user links their external account (e.g. Discord user ID)
    to a JARVIS principal.
    """

    @property
    def id_label(self) -> str:
        """Human-readable label for the external account ID (e.g. ``"Discord user ID"``)."""
        return "account ID"

    def normalize_allow_entry(self, raw: str) -> str | None:
        """Normalise a raw allow-entry string to a canonical account identifier.

        Returns ``None`` to reject invalid entries. Default passes through.
        """
        stripped = raw.strip()
        return stripped if stripped else None

    def notify_approval(self, ctx: dict[str, Any]) -> None:
        """Called after an account pairing is approved.

        ``ctx`` contains ``account_id``, ``principal_id``, and transport facts.
        Override to send a confirmation message on the channel.
        """


class ChannelThreadingAdapter(ABC):
    """Threading adapter for a channel plugin.

    Mirrors OpenClaw's ``ChannelThreadingAdapter`` type. Decides how JARVIS
    replies within threaded transports (Slack threads, Discord threads, etc.).
    """

    def resolve_reply_to_mode(self, ctx: dict[str, Any]) -> str:
        """Return the reply-to mode for an inbound message.

        Common return values:
        - ``"thread"`` — reply in the same thread.
        - ``"channel"`` — reply in the top-level channel.
        - ``"dm"`` — reply via DM.
        Default: ``"thread"``.
        """
        return "thread"


class ChannelOutboundAdapter(ABC):
    """Outbound rendering adapter for a channel plugin.

    Mirrors OpenClaw's ``ChannelOutboundAdapter`` type. Handles transport-
    specific rendering of outbound message payloads. Override only the
    render methods your transport supports.
    """

    async def send_text(self, target: str, text: str, ctx: dict[str, Any]) -> dict[str, Any]:
        """Send a plain-text message. Returns a transport receipt dict."""
        raise NotImplementedError("send_text not implemented")

    async def send_media(
        self, target: str, media: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a media attachment (image, audio, video, file).

        ``media`` has at least ``{"type": str, "url": str | None, "data": bytes | None}``.
        """
        raise NotImplementedError("send_media not implemented")

    async def send_poll(
        self, target: str, poll: dict[str, Any], ctx: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a poll / interactive choice to the transport.

        ``poll`` has at least ``{"question": str, "options": list[str]}``.
        """
        raise NotImplementedError("send_poll not implemented")


class ChannelConversationBindings(ABC):
    """Conversation binding lifecycle adapter.

    Mirrors OpenClaw's ``ChannelConversationBindings`` type. Manages the
    relationship between external conversations (e.g. a Slack channel) and
    JARVIS sessions.
    """

    def resolve_binding_key(self, ctx: dict[str, Any]) -> str | None:
        """Return a stable binding key for an inbound conversation context.

        The key is used to look up / create the JARVIS session for this
        conversation. Return ``None`` to fall back to the default per-sender
        session routing.
        """
        return None

    def on_binding_resolved(self, ctx: dict[str, Any]) -> None:
        """Called after a conversation binding is resolved or created."""


__all__ = [
    "ChannelConversationBindings",
    "ChannelOutboundAdapter",
    "ChannelPairingAdapter",
    "ChannelSecurityAdapter",
    "ChannelThreadingAdapter",
]
