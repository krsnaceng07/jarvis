"""
Registry for music generation providers.
"""

from typing import Optional, Any
from .types import MusicGenerationProvider

_providers: dict[str, MusicGenerationProvider] = {}


def register_music_generation_provider(provider: MusicGenerationProvider) -> None:
    """Register a music generation provider."""
    if provider.id in _providers:
        raise ValueError(f"Music generation provider {provider.id} is already registered.")
    _providers[provider.id] = provider


def get_music_generation_provider(
    provider_id: str, cfg: Optional[Any] = None
) -> Optional[MusicGenerationProvider]:
    """Get a registered music generation provider by ID."""
    return _providers.get(provider_id)


def list_music_generation_providers(cfg: Optional[Any] = None) -> list[MusicGenerationProvider]:
    """List all registered music generation providers."""
    return list(_providers.values())
