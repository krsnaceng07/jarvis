"""JARVIS video-generation-core (shared core package - not a plugin).

Mirrors OpenClaw's ``extensions/video-generation-core/`` shape:
OpenClaw ships this as a runtime package (no ``openclaw.plugin.json``),
so JARVIS mirrors that with ``pyproject.toml`` + ``__init__.py`` re-exports
from ``jarvis_sdk.video_generation``.
"""

from __future__ import annotations

from jarvis_sdk.video_generation import (
    GeneratedVideoAsset,
    VideoGenerationAspectRatio,
    VideoGenerationGeometryCapabilities,
    VideoGenerationModeCapabilities,
    VideoGenerationProvider,
    VideoGenerationProviderCapabilities,
    VideoGenerationProviderConfiguredContext,
    VideoGenerationRequest,
    VideoGenerationResolution,
    VideoGenerationResult,
    VideoGenerationSourceImage,
    VideoGenerationSourceVideo,
)

__all__ = [
    "GeneratedVideoAsset",
    "VideoGenerationAspectRatio",
    "VideoGenerationGeometryCapabilities",
    "VideoGenerationModeCapabilities",
    "VideoGenerationProvider",
    "VideoGenerationProviderCapabilities",
    "VideoGenerationProviderConfiguredContext",
    "VideoGenerationRequest",
    "VideoGenerationResolution",
    "VideoGenerationResult",
    "VideoGenerationSourceImage",
    "VideoGenerationSourceVideo",
]
