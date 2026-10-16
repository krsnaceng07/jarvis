"""
Text-to-speech core logic and types.
"""

from .types import (
    TtsProvider,
    TtsProviderCapabilities,
    TtsRequest,
    TtsResult,
    GenerateTtsParams,
    GenerateTtsRuntimeResult,
    TtsModeCapabilities,
    TtsOutputCapabilities,
    GeneratedTtsAsset,
)
from .runtime import generate_tts

__all__ = [
    "TtsProvider",
    "TtsProviderCapabilities",
    "TtsRequest",
    "TtsResult",
    "GenerateTtsParams",
    "GenerateTtsRuntimeResult",
    "TtsModeCapabilities",
    "TtsOutputCapabilities",
    "GeneratedTtsAsset",
    "generate_tts",
]
