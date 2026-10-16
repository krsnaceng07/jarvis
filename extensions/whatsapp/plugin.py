"""WhatsApp channel plugin definition.

OpenClaw parity: mirrors the OpenClaw ``whatsapp`` channel extension.
Binds channel send/listen contracts with Desktop/Web provider execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_sdk import ChannelPlugin, Result


@dataclass(frozen=True, slots=True)
class WhatsAppPlugin(ChannelPlugin):
    """WhatsApp channel descriptor and provider coordinator."""

    id: str = "whatsapp"
    name: str = "WhatsApp"
    kind: str = "channel"
    base_url: str = "https://graph.facebook.com/v17.0"
    poll_interval_sec: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)
    on_message: Any = None

    def init(self, ctx: Any) -> None:
        """Channel init hook (auth + connection)."""
        return None

    async def send(self, target: str, message: Any):  # type: ignore[override]
        """Send a message to a target on this channel with desktop/provider fallback."""
        text = str(
            message.get("text", "")
            if isinstance(message, dict)
            else getattr(message, "text", None) or message
        )
        if not target:
            return Result.err("missing_target", "Target recipient is required")
        if not text:
            return Result.err("empty_message", "Message text cannot be empty")

        # Try desktop provider
        try:
            from src.desktop_automation.providers.whatsapp_provider import WhatsAppDesktopProvider

            provider = WhatsAppDesktopProvider()
            res = await provider.send_message(target, text)
            if res.ok:
                return Result.ok(res.evidence)
            return Result.err("provider_error", res.error or "Failed to send message via provider")
        except Exception as exc:
            return Result.err("send_exception", str(exc))

    async def listen(self, callback: Any) -> None:  # type: ignore[override]
        """Start listening for inbound messages."""
        raise NotImplementedError(
            "WhatsApp inbound transport is not implemented; listener is unavailable"
        )


whatsapp_plugin = WhatsAppPlugin()
entry = whatsapp_plugin
