"""
Registry for text-to-speech providers.
"""

from typing import Optional, Any
from .types import TtsProvider

_providers: dict[str, TtsProvider] = {}


def register_tts_provider(provider: TtsProvider) -> None:
    """Register a text-to-speech provider."""
    if provider.id in _providers:
        raise ValueError(f"TTS provider {provider.id} is already registered.")
    _providers[provider.id] = provider


def get_tts_provider(provider_id: str, cfg: Optional[Any] = None) -> Optional[TtsProvider]:
    """Get a registered TTS provider by ID."""
    return _providers.get(provider_id)


def list_tts_providers(cfg: Optional[Any] = None) -> list[TtsProvider]:
    """List all registered TTS providers."""
    return list(_providers.values())
