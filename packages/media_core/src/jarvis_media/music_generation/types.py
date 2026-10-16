"""
Shared music-generation request, provider, capability, and result contracts.
Mirrors openclaw's music-generation/types.ts and runtime-types.ts.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Any, Protocol


MusicGenerationAudioFormat = Literal["mp3", "wav", "aac", "flac"]


@dataclass
class GeneratedMusicAsset:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class MusicGenerationSourceAudio:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class MusicGenerationProviderConfiguredContext:
    cfg: Any
    agent_dir: Optional[str] = None


@dataclass
class MusicGenerationProviderOptions:
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MusicGenerationRequest:
    provider: str
    model: str
    prompt: str
    cfg: Any
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    timeout_ms: Optional[int] = None
    duration_seconds: Optional[int] = None
    instrumental: Optional[bool] = None
    lyrics: Optional[str] = None
    style: Optional[str] = None
    image: Optional[str] = None
    images: Optional[list[str]] = None
    format: Optional[Literal["mp3", "wav"]] = None
    filename: Optional[str] = None
    provider_options: Optional[MusicGenerationProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class MusicGenerationResult:
    tracks: list[GeneratedMusicAsset]
    model: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class MusicGenerationModeCapabilities:
    supports_text_to_music: bool = True
    supports_audio_to_music: bool = False
    max_duration_seconds: Optional[int] = None
    supports_instrumental_toggle: bool = False
    supports_lyrics_input: bool = False
    max_input_images: Optional[int] = None


@dataclass
class MusicGenerationOutputCapabilities:
    formats: Optional[list[MusicGenerationAudioFormat]] = None
    formats_by_model: Optional[dict[str, list[MusicGenerationAudioFormat]]] = None


@dataclass
class MusicGenerationProviderCapabilities:
    generate: MusicGenerationModeCapabilities
    output: Optional[MusicGenerationOutputCapabilities] = None


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


@dataclass
class GenerateMusicParams:
    cfg: Any
    prompt: str
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    model_override: Optional[str] = None
    duration_seconds: Optional[int] = None
    instrumental: Optional[bool] = None
    lyrics: Optional[str] = None
    style: Optional[str] = None
    image: Optional[str] = None
    images: Optional[list[str]] = None
    format: Optional[Literal["mp3", "wav"]] = None
    filename: Optional[str] = None
    auto_provider_fallback: Optional[bool] = None
    timeout_ms: Optional[int] = None
    provider_options: Optional[MusicGenerationProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class GenerateMusicRuntimeResult:
    tracks: list[GeneratedMusicAsset]
    provider: str
    model: str
    metadata: Optional[dict[str, Any]] = None
