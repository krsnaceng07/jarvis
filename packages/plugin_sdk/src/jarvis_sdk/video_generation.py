"""
Video generation interfaces for JARVIS Plugin SDK.
These map to the core media abstractions.
"""

from typing import Literal, Optional, Any, Protocol

VideoGenerationResolution = Literal["720p", "1080p", "4k"]
VideoGenerationAspectRatio = Literal["16:9", "9:16", "1:1", "4:3", "3:4"]


class GeneratedVideoAsset(Protocol):
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    metadata: Optional[dict[str, Any]]


class VideoGenerationSourceImage(Protocol):
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    metadata: Optional[dict[str, Any]]


class VideoGenerationSourceVideo(Protocol):
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    metadata: Optional[dict[str, Any]]


class VideoGenerationRequest(Protocol):
    provider: str
    model: str
    prompt: str
    cfg: Any
    agent_dir: Optional[str]
    auth_store: Optional[Any]
    timeout_ms: Optional[int]
    aspect_ratio: Optional[VideoGenerationAspectRatio]
    resolution: Optional[VideoGenerationResolution]
    duration_seconds: Optional[int]
    fps: Optional[int]
    input_images: Optional[list[VideoGenerationSourceImage]]
    input_video: Optional[VideoGenerationSourceVideo]
    provider_options: Optional[Any]
    ssrf_policy: Optional[Any]


class VideoGenerationResult(Protocol):
    videos: list[GeneratedVideoAsset]
    model: Optional[str]
    metadata: Optional[dict[str, Any]]


class VideoGenerationProviderConfiguredContext(Protocol):
    cfg: Any
    agent_dir: Optional[str]


class VideoGenerationModeCapabilities(Protocol):
    supports_text_to_video: bool
    supports_image_to_video: bool
    supports_video_to_video: bool
    max_duration_seconds: Optional[int]
    max_fps: Optional[int]


class VideoGenerationGeometryCapabilities(Protocol):
    aspect_ratios: Optional[list[VideoGenerationAspectRatio]]
    aspect_ratios_by_model: Optional[dict[str, list[VideoGenerationAspectRatio]]]
    resolutions: Optional[list[VideoGenerationResolution]]
    resolutions_by_model: Optional[dict[str, list[VideoGenerationResolution]]]


class VideoGenerationProviderCapabilities(Protocol):
    generate: VideoGenerationModeCapabilities
    geometry: Optional[VideoGenerationGeometryCapabilities]


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
