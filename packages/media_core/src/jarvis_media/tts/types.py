"""
Shared text-to-speech request, provider, capability, and result contracts.
Mirrors openclaw's tts/types.ts and runtime-types.ts.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Any, Protocol


TtsAudioFormat = Literal["mp3", "wav", "aac", "flac", "pcm"]


@dataclass
class GeneratedTtsAsset:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class TtsProviderConfiguredContext:
    cfg: Any
    agent_dir: Optional[str] = None


@dataclass
class TtsProviderOptions:
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TtsRequest:
    provider: str
    model: str
    text: str
    voice: Optional[str] = None
    cfg: Any = None
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    timeout_ms: Optional[int] = None
    speed: Optional[float] = None
    pitch: Optional[float] = None
    output_format: Optional[TtsAudioFormat] = None
    provider_options: Optional[TtsProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class TtsResult:
    audio: GeneratedTtsAsset
    model: Optional[str] = None
    voice: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class TtsModeCapabilities:
    supports_speed: bool = False
    supports_pitch: bool = False


@dataclass
class TtsOutputCapabilities:
    formats: Optional[list[TtsAudioFormat]] = None
    formats_by_model: Optional[dict[str, list[TtsAudioFormat]]] = None


@dataclass
class TtsProviderCapabilities:
    generate: TtsModeCapabilities
    output: Optional[TtsOutputCapabilities] = None


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


@dataclass
class GenerateTtsParams:
    cfg: Any
    text: str
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    model_override: Optional[str] = None
    voice_override: Optional[str] = None
    speed: Optional[float] = None
    pitch: Optional[float] = None
    output_format: Optional[TtsAudioFormat] = None
    auto_provider_fallback: Optional[bool] = None
    timeout_ms: Optional[int] = None
    provider_options: Optional[TtsProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class GenerateTtsRuntimeResult:
    audio: GeneratedTtsAsset
    provider: str
    model: str
    voice: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
