"""
Registry for video generation providers.
"""

from typing import Optional, Any
from .types import VideoGenerationProvider

_providers: dict[str, VideoGenerationProvider] = {}


def register_video_generation_provider(provider: VideoGenerationProvider) -> None:
    """Register a video generation provider."""
    if provider.id in _providers:
        raise ValueError(f"Video generation provider {provider.id} is already registered.")
    _providers[provider.id] = provider


def get_video_generation_provider(
    provider_id: str, cfg: Optional[Any] = None
) -> Optional[VideoGenerationProvider]:
    """Get a registered video generation provider by ID."""
    return _providers.get(provider_id)


def list_video_generation_providers(cfg: Optional[Any] = None) -> list[VideoGenerationProvider]:
    """List all registered video generation providers."""
    return list(_providers.values())
