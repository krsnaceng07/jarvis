"""
Speech-to-text interfaces for JARVIS Plugin SDK.
These map to the core media abstractions.
"""

from typing import Optional, Any, Protocol


class SttRequest(Protocol):
    provider: str
    model: str
    audio_base64: Optional[str]
    audio_url: Optional[str]
    audio_mime_type: str
    language: Optional[str]
    cfg: Any
    agent_dir: Optional[str]
    auth_store: Optional[Any]
    timeout_ms: Optional[int]
    provider_options: Optional[Any]
    ssrf_policy: Optional[Any]


class SttResult(Protocol):
    text: str
    language: Optional[str]
    model: Optional[str]
    metadata: Optional[dict[str, Any]]


class SttProviderConfiguredContext(Protocol):
    cfg: Any
    agent_dir: Optional[str]


class SttModeCapabilities(Protocol):
    supports_batch: bool
    supports_streaming: bool
    supports_language_detection: bool


class SttProviderCapabilities(Protocol):
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
