"""
Text-to-speech interfaces for JARVIS Plugin SDK.
These map to the core media abstractions.
"""

from typing import Literal, Optional, Any, Protocol

TtsAudioFormat = Literal["mp3", "wav", "aac", "flac", "pcm"]


class GeneratedTtsAsset(Protocol):
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    metadata: Optional[dict[str, Any]]


class TtsRequest(Protocol):
    provider: str
    model: str
    text: str
    voice: Optional[str]
    cfg: Any
    agent_dir: Optional[str]
    auth_store: Optional[Any]
    timeout_ms: Optional[int]
    speed: Optional[float]
    pitch: Optional[float]
    output_format: Optional[TtsAudioFormat]
    provider_options: Optional[Any]
    ssrf_policy: Optional[Any]


class TtsResult(Protocol):
    audio: GeneratedTtsAsset
    model: Optional[str]
    voice: Optional[str]
    metadata: Optional[dict[str, Any]]


class TtsProviderConfiguredContext(Protocol):
    cfg: Any
    agent_dir: Optional[str]


class TtsModeCapabilities(Protocol):
    supports_speed: bool
    supports_pitch: bool


class TtsOutputCapabilities(Protocol):
    formats: Optional[list[TtsAudioFormat]]
    formats_by_model: Optional[dict[str, list[TtsAudioFormat]]]


class TtsProviderCapabilities(Protocol):
    generate: TtsModeCapabilities
    output: Optional[TtsOutputCapabilities]


class TtsProvider(Protocol):
    id: str
    aliases: Optional[list[str]]
    label: Optional[str]
    default_model: Optional[str]
    default_voice: Optional[str]
    default_timeout_ms: Optional[int]
    models: Optional[list[str]]
    voices: Optional[list[str]]
    capabilities: TtsProviderCapabilities

    def is_configured(self, ctx: TtsProviderConfiguredContext) -> bool: ...

    async def generate_tts(self, req: TtsRequest) -> TtsResult: ...
