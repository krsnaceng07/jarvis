"""jarvis.plugins.capability_registry — Capability ownership model & plugin capability registry.

OpenClaw parity: mirrors
``openclaw-main/docs/plugins/capability-model.md`` and
``openclaw-main/src/plugins/registry-registrars-capabilities.ts``.

Rule: plugin = ownership boundary, capability = shared core contract.

Capabilities managed:
- EmbeddingProvider
- SpeechProvider
- RealtimeTranscriptionProvider
- RealtimeVoiceProvider
- MediaUnderstandingProvider
- ImageGenerationProvider
- VideoGenerationProvider
- WebFetchProvider
- WebSearchProvider
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapabilityRegistration:
    capability_type: str
    id: str
    label: str
    plugin_id: str
    provider_config: dict[str, Any] = field(default_factory=dict)


class CapabilityRegistry:
    """Central registry enforcing capability contracts across vendor plugins."""

    def __init__(self) -> None:
        self.embedding_providers: dict[str, CapabilityRegistration] = {}
        self.speech_providers: dict[str, CapabilityRegistration] = {}
        self.transcription_providers: dict[str, CapabilityRegistration] = {}
        self.voice_providers: dict[str, CapabilityRegistration] = {}
        self.media_understanding_providers: dict[str, CapabilityRegistration] = {}
        self.image_generation_providers: dict[str, CapabilityRegistration] = {}
        self.video_generation_providers: dict[str, CapabilityRegistration] = {}
        self.web_fetch_providers: dict[str, CapabilityRegistration] = {}
        self.web_search_providers: dict[str, CapabilityRegistration] = {}

    def register_embedding_provider(self, plugin_id: str, id: str, config: dict[str, Any]) -> CapabilityRegistration:
        reg = CapabilityRegistration("embedding", id, config.get("label", id), plugin_id, config)
        self.embedding_providers[id] = reg
        return reg

    def register_speech_provider(self, plugin_id: str, id: str, config: dict[str, Any]) -> CapabilityRegistration:
        reg = CapabilityRegistration("speech", id, config.get("label", id), plugin_id, config)
        self.speech_providers[id] = reg
        return reg

    def register_image_generation_provider(self, plugin_id: str, id: str, config: dict[str, Any]) -> CapabilityRegistration:
        reg = CapabilityRegistration("image_generation", id, config.get("label", id), plugin_id, config)
        self.image_generation_providers[id] = reg
        return reg

    def register_video_generation_provider(self, plugin_id: str, id: str, config: dict[str, Any]) -> CapabilityRegistration:
        reg = CapabilityRegistration("video_generation", id, config.get("label", id), plugin_id, config)
        self.video_generation_providers[id] = reg
        return reg

    def register_web_fetch_provider(self, plugin_id: str, id: str, config: dict[str, Any]) -> CapabilityRegistration:
        reg = CapabilityRegistration("web_fetch", id, config.get("label", id), plugin_id, config)
        self.web_fetch_providers[id] = reg
        return reg

    def register_web_search_provider(self, plugin_id: str, id: str, config: dict[str, Any]) -> CapabilityRegistration:
        reg = CapabilityRegistration("web_search", id, config.get("label", id), plugin_id, config)
        self.web_search_providers[id] = reg
        return reg


GLOBAL_CAPABILITY_REGISTRY = CapabilityRegistry()

__all__ = [
    "GLOBAL_CAPABILITY_REGISTRY",
    "CapabilityRegistration",
    "CapabilityRegistry",
]
