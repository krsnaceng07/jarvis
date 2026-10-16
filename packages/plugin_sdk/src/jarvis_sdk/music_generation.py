"""
Music generation interfaces for JARVIS Plugin SDK.
These map to the core media abstractions.
"""

from typing import Literal, Optional, Any, Protocol

MusicGenerationAudioFormat = Literal["mp3", "wav", "aac", "flac"]


class GeneratedMusicAsset(Protocol):
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    metadata: Optional[dict[str, Any]]


class MusicGenerationSourceAudio(Protocol):
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    metadata: Optional[dict[str, Any]]


class MusicGenerationRequest(Protocol):
    provider: str
    model: str
    prompt: str
    cfg: Any
    agent_dir: Optional[str]
    auth_store: Optional[Any]
    timeout_ms: Optional[int]
    duration_seconds: Optional[int]
    instrumental: Optional[bool]
    lyrics: Optional[str]
    style: Optional[str]
    input_audio: Optional[MusicGenerationSourceAudio]
    provider_options: Optional[Any]
    ssrf_policy: Optional[Any]


class MusicGenerationResult(Protocol):
    tracks: list[GeneratedMusicAsset]
    model: Optional[str]
    metadata: Optional[dict[str, Any]]


class MusicGenerationProviderConfiguredContext(Protocol):
    cfg: Any
    agent_dir: Optional[str]


class MusicGenerationModeCapabilities(Protocol):
    supports_text_to_music: bool
    supports_audio_to_music: bool
    max_duration_seconds: Optional[int]
    supports_instrumental_toggle: bool
    supports_lyrics_input: bool


class MusicGenerationOutputCapabilities(Protocol):
    formats: Optional[list[MusicGenerationAudioFormat]]
    formats_by_model: Optional[dict[str, list[MusicGenerationAudioFormat]]]


class MusicGenerationProviderCapabilities(Protocol):
    generate: MusicGenerationModeCapabilities
    output: Optional[MusicGenerationOutputCapabilities]


class MusicGenerationProvider(Protocol):
    id: str
    aliases: Optional[list[str]]
    label: Optional[str]
    default_model: Optional[str]
    default_timeout_ms: Optional[int]
    models: Optional[list[str]]
    capabilities: MusicGenerationProviderCapabilities

    def is_configured(self, ctx: MusicGenerationProviderConfiguredContext) -> bool: ...

    async def generate_music(self, req: MusicGenerationRequest) -> MusicGenerationResult: ...
