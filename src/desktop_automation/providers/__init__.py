"""jarvis.desktop_automation.providers — Messaging & application providers."""

from .base_provider import (
    ApplicationState,
    BaseMessagingProvider,
    CompletionStatus,
    ContactCandidate,
    MessageDraft,
    ProviderActionResult,
)
from .registry import ProviderRegistry
from .whatsapp_provider import WhatsAppDesktopProvider

__all__ = [
    "ApplicationState",
    "BaseMessagingProvider",
    "CompletionStatus",
    "ContactCandidate",
    "MessageDraft",
    "ProviderActionResult",
    "ProviderRegistry",
    "WhatsAppDesktopProvider",
]
