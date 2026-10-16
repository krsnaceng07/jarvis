"""jarvis.desktop_automation.providers.registry — Central provider registry.

OpenClaw parity: Resolves messaging and application providers dynamically
by capability and application ID without hardcoding application branches in core.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base_provider import BaseMessagingProvider


class ProviderRegistry:
    """Singleton registry for desktop and messaging automation providers."""

    _instance: Optional[ProviderRegistry] = None

    def __init__(self) -> None:
        self._providers: Dict[str, BaseMessagingProvider] = {}

    @classmethod
    def get_instance(cls) -> ProviderRegistry:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_default_providers()
        return cls._instance

    def _register_default_providers(self) -> None:
        """Register built-in providers lazily."""
        try:
            from .whatsapp_provider import WhatsAppDesktopProvider
            self.register_provider(WhatsAppDesktopProvider())
        except Exception:
            pass

    def register_provider(self, provider: BaseMessagingProvider) -> None:
        """Register a messaging provider instance."""
        self._providers[provider.app_id.lower()] = provider

    def get_provider(self, app_id: str) -> Optional[BaseMessagingProvider]:
        """Resolve a messaging provider by application ID."""
        return self._providers.get(app_id.lower())

    def list_providers(self) -> List[str]:
        """List registered provider IDs."""
        return list(self._providers.keys())
