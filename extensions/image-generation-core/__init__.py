"""JARVIS image-generation-core (shared core package - not a plugin).

Mirrors OpenClaw's ``extensions/image-generation-core/`` shape:
OpenClaw ships this as a runtime package (no ``openclaw.plugin.json``),
so JARVIS mirrors that with ``pyproject.toml`` + ``__init__.py`` re-exports
from ``jarvis_sdk.image_generation``.
"""

from __future__ import annotations

from jarvis_sdk.image_generation import (
    GeneratedImageAsset,
    ImageGenerationBackground,
    ImageGenerationEditCapabilities,
    ImageGenerationGeometryCapabilities,
    ImageGenerationModeCapabilities,
    ImageGenerationOutputCapabilities,
    ImageGenerationOutputFormat,
    ImageGenerationProvider,
    ImageGenerationProviderCapabilities,
    ImageGenerationProviderConfiguredContext,
    ImageGenerationQuality,
    ImageGenerationRequest,
    ImageGenerationResolution,
    ImageGenerationResult,
    ImageGenerationSourceImage,
)

__all__ = [
    "GeneratedImageAsset",
    "ImageGenerationBackground",
    "ImageGenerationEditCapabilities",
    "ImageGenerationGeometryCapabilities",
    "ImageGenerationModeCapabilities",
    "ImageGenerationOutputCapabilities",
    "ImageGenerationOutputFormat",
    "ImageGenerationProvider",
    "ImageGenerationProviderCapabilities",
    "ImageGenerationProviderConfiguredContext",
    "ImageGenerationQuality",
    "ImageGenerationRequest",
    "ImageGenerationResolution",
    "ImageGenerationResult",
    "ImageGenerationSourceImage",
]
