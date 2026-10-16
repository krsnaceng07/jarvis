"""
Shared speech-to-text request, provider, capability, and result contracts.
Mirrors openclaw's stt/types.ts and runtime-types.ts.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Protocol


@dataclass
class SttProviderConfiguredContext:
    cfg: Any
    agent_dir: Optional[str] = None


@dataclass
class SttProviderOptions:
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SttRequest:
    provider: str
    model: str
    audio_base64: Optional[str] = None
    audio_url: Optional[str] = None
    audio_mime_type: str = "audio/wav"
    language: Optional[str] = None
    cfg: Any = None
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    timeout_ms: Optional[int] = None
    provider_options: Optional[SttProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class SttResult:
    text: str
    language: Optional[str] = None
    model: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class SttModeCapabilities:
    supports_batch: bool = True
    supports_streaming: bool = False
    supports_language_detection: bool = False


@dataclass
class SttProviderCapabilities:
    transcribe: SttModeCapabilities


class SttProvider(Protocol):
    id: str
    aliases: Optional[list[str]]
    label: Optional[str]
    default_model: Optional[str]
    default_timeout_ms: Optional[int]
    models: Optional[list[str]]
    capabilities: SttProviderCapabilities

    def is_configured(self, ctx: SttProviderConfiguredContext) -> bool: ...

    async def transcribe_audio(self, req: SttRequest) -> SttResult: ...


@dataclass
class GenerateSttParams:
    cfg: Any
    audio_base64: Optional[str] = None
    audio_url: Optional[str] = None
    audio_mime_type: str = "audio/wav"
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    model_override: Optional[str] = None
    language: Optional[str] = None
    auto_provider_fallback: Optional[bool] = None
    timeout_ms: Optional[int] = None
    provider_options: Optional[SttProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class GenerateSttRuntimeResult:
    text: str
    provider: str
    model: str
    language: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
