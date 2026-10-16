"""
Registry for image generation providers.
"""

from typing import Optional, Any
from .types import ImageGenerationProvider

_providers: dict[str, ImageGenerationProvider] = {}


def register_image_generation_provider(provider: ImageGenerationProvider) -> None:
    """Register an image generation provider."""
    if provider.id in _providers:
        raise ValueError(f"Image generation provider {provider.id} is already registered.")
    _providers[provider.id] = provider


def get_image_generation_provider(
    provider_id: str, cfg: Optional[Any] = None
) -> Optional[ImageGenerationProvider]:
    """Get a registered image generation provider by ID."""
    return _providers.get(provider_id)


def list_image_generation_providers(cfg: Optional[Any] = None) -> list[ImageGenerationProvider]:
    """List all registered image generation providers."""
    return list(_providers.values())
