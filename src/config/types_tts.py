"""jarvis.config.types_tts — text-to-speech config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.tts.ts``.
"""
from __future__ import annotations

from typing import TypedDict


#: Provider id for TTS.
TtsProvider = str
#: TTS application mode.
TtsMode = str  # "final" | "all"
#: Auto-TTS mode.
TtsAutoMode = str  # "off" | "always" | "inbound" | "tagged"


class TtsModelOverrideConfig(TypedDict, total=False):
    """Model-provided overrides for TTS."""

    enabled: bool
    allowText: bool
    allowProvider: bool
    allowVoice: bool
    allowModelId: bool
    allowVoiceSettings: bool
    allowNormalization: bool
    allowSeed: bool


#: Provider-specific TTS settings keyed by speech provider id.
TtsProviderConfigMap = dict


#: Persona fallback policy.
TtsPersonaFallbackPolicy = str  # "preserve-persona" | "provider-defaults" | "fail"


class TtsPersonaPromptConfig(TypedDict, total=False):
    profile: str
    scene: str
    sampleContext: str
    style: str
    accent: str
    pacing: str
    constraints: list


class TtsPersonaConfig(TypedDict, total=False):
    label: str
    description: str
    provider: str
    fallbackPolicy: str
    prompt: TtsPersonaPromptConfig
    providers: dict


class ResolvedTtsPersona(TypedDict, total=False):
    """Resolved TTS persona with required id field."""

    id: str
    label: str
    description: str
    provider: str
    fallbackPolicy: str
    prompt: TtsPersonaPromptConfig
    providers: dict


class TtsConfig(TypedDict, total=False):
    auto: str
    enabled: bool
    mode: str
    provider: str
    persona: str
    personas: dict
    summaryModel: str
    modelOverrides: TtsModelOverrideConfig
    providers: dict
    prefsPath: str
    maxTextLength: int
    timeoutMs: int


__all__ = [
    "TtsProvider",
    "TtsMode",
    "TtsAutoMode",
    "TtsModelOverrideConfig",
    "TtsProviderConfigMap",
    "TtsPersonaFallbackPolicy",
    "TtsPersonaPromptConfig",
    "TtsPersonaConfig",
    "ResolvedTtsPersona",
    "TtsConfig",
]
