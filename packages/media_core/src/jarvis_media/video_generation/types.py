"""
Shared video-generation request, provider, capability, and result contracts.
Mirrors openclaw's video-generation/types.ts and runtime-types.ts.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Any, Protocol


VideoGenerationResolution = Literal["720p", "1080p", "4k"]
VideoGenerationAspectRatio = Literal["16:9", "9:16", "1:1", "4:3", "3:4"]


@dataclass
class GeneratedVideoAsset:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class VideoGenerationSourceImage:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class VideoGenerationSourceVideo:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class VideoGenerationProviderConfiguredContext:
    cfg: Any
    agent_dir: Optional[str] = None


@dataclass
class VideoGenerationProviderOptions:
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoGenerationRequest:
    provider: str
    model: str
    prompt: str
    cfg: Any
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    timeout_ms: Optional[int] = None
    aspect_ratio: Optional[VideoGenerationAspectRatio] = None
    resolution: Optional[VideoGenerationResolution] = None
    duration_seconds: Optional[int] = None
    fps: Optional[int] = None
    input_images: Optional[list[VideoGenerationSourceImage]] = None
    input_video: Optional[VideoGenerationSourceVideo] = None
    provider_options: Optional[VideoGenerationProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class VideoGenerationResult:
    videos: list[GeneratedVideoAsset]
    model: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class VideoGenerationModeCapabilities:
    supports_text_to_video: bool = True
    supports_image_to_video: bool = False
    supports_video_to_video: bool = False
    max_duration_seconds: Optional[int] = None
    max_fps: Optional[int] = None


@dataclass
class VideoGenerationGeometryCapabilities:
    aspect_ratios: Optional[list[VideoGenerationAspectRatio]] = None
    aspect_ratios_by_model: Optional[dict[str, list[VideoGenerationAspectRatio]]] = None
    resolutions: Optional[list[VideoGenerationResolution]] = None
    resolutions_by_model: Optional[dict[str, list[VideoGenerationResolution]]] = None


@dataclass
class VideoGenerationProviderCapabilities:
    generate: VideoGenerationModeCapabilities
    geometry: Optional[VideoGenerationGeometryCapabilities] = None


class VideoGenerationProvider(Protocol):
    id: str
    aliases: Optional[list[str]]
    label: Optional[str]
    default_model: Optional[str]
    default_timeout_ms: Optional[int]
    models: Optional[list[str]]
    capabilities: VideoGenerationProviderCapabilities

    def is_configured(self, ctx: VideoGenerationProviderConfiguredContext) -> bool: ...

    async def generate_video(self, req: VideoGenerationRequest) -> VideoGenerationResult: ...


@dataclass
class FallbackAttempt:
    provider: str
    model: str
    error: str
    reason: Optional[str] = None
    status: Optional[int] = None
    code: Optional[str] = None


@dataclass
class GenerateVideoParams:
    cfg: Any
    prompt: str
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    model_override: Optional[str] = None
    aspect_ratio: Optional[VideoGenerationAspectRatio] = None
    resolution: Optional[VideoGenerationResolution] = None
    duration_seconds: Optional[int] = None
    fps: Optional[int] = None
    input_images: Optional[list[VideoGenerationSourceImage]] = None
    input_video: Optional[VideoGenerationSourceVideo] = None
    auto_provider_fallback: Optional[bool] = None
    timeout_ms: Optional[int] = None
    provider_options: Optional[VideoGenerationProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class GenerateVideoRuntimeResult:
    videos: list[GeneratedVideoAsset]
    provider: str
    model: str
    attempts: list[FallbackAttempt] = field(default_factory=list)
    metadata: Optional[dict[str, Any]] = None
