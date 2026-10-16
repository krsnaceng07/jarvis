"""
Speech-to-text core logic and types.
"""

from .types import (
    SttProvider,
    SttProviderCapabilities,
    SttRequest,
    SttResult,
    GenerateSttParams,
    GenerateSttRuntimeResult,
    SttModeCapabilities,
)
from .runtime import transcribe_audio

__all__ = [
    "SttProvider",
    "SttProviderCapabilities",
    "SttRequest",
    "SttResult",
    "GenerateSttParams",
    "GenerateSttRuntimeResult",
    "SttModeCapabilities",
    "transcribe_audio",
]
