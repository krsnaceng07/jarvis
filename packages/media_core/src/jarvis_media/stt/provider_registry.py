"""
Registry for speech-to-text providers.
"""

from typing import Optional, Any
from .types import SttProvider

_providers: dict[str, SttProvider] = {}


def register_stt_provider(provider: SttProvider) -> None:
    """Register a speech-to-text provider."""
    if provider.id in _providers:
        raise ValueError(f"STT provider {provider.id} is already registered.")
    _providers[provider.id] = provider


def get_stt_provider(provider_id: str, cfg: Optional[Any] = None) -> Optional[SttProvider]:
    """Get a registered STT provider by ID."""
    return _providers.get(provider_id)


def list_stt_providers(cfg: Optional[Any] = None) -> list[SttProvider]:
    """List all registered STT providers."""
    return list(_providers.values())
