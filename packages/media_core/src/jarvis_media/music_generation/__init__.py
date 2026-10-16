"""
Music generation core logic and types.
"""

from .types import (
    MusicGenerationProvider,
    MusicGenerationProviderCapabilities,
    MusicGenerationRequest,
    MusicGenerationResult,
    GenerateMusicParams,
    GenerateMusicRuntimeResult,
    MusicGenerationModeCapabilities,
    MusicGenerationOutputCapabilities,
    GeneratedMusicAsset,
    MusicGenerationSourceAudio,
)
from .runtime import generate_music

__all__ = [
    "MusicGenerationProvider",
    "MusicGenerationProviderCapabilities",
    "MusicGenerationRequest",
    "MusicGenerationResult",
    "GenerateMusicParams",
    "GenerateMusicRuntimeResult",
    "MusicGenerationModeCapabilities",
    "MusicGenerationOutputCapabilities",
    "GeneratedMusicAsset",
    "MusicGenerationSourceAudio",
    "generate_music",
]
