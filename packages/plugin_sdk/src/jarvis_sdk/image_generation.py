"""
Image generation interfaces for JARVIS Plugin SDK.
These map to the core media abstractions.
"""

from typing import Literal, Optional, Any, Protocol

ImageGenerationResolution = Literal["1K", "2K", "4K"]
ImageGenerationQuality = Literal["low", "medium", "high", "auto"]
ImageGenerationOutputFormat = Literal["png", "jpeg", "webp"]
ImageGenerationBackground = Literal["transparent", "opaque", "auto"]


class ImageGenerationSourceImage:
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    metadata: Optional[dict[str, Any]]


class ImageGenerationRequest(Protocol):
    provider: str
    model: str
    prompt: str
    cfg: Any
    agent_dir: Optional[str]
    auth_store: Optional[Any]
    timeout_ms: Optional[int]
    count: Optional[int]
    size: Optional[str]
    aspect_ratio: Optional[str]
    resolution: Optional[ImageGenerationResolution]
    quality: Optional[ImageGenerationQuality]
    output_format: Optional[ImageGenerationOutputFormat]
    background: Optional[ImageGenerationBackground]
    input_images: Optional[list[ImageGenerationSourceImage]]
    provider_options: Optional[Any]
    ssrf_policy: Optional[Any]


class GeneratedImageAsset(Protocol):
    buffer: bytes
    mime_type: str
    file_name: Optional[str]
    revised_prompt: Optional[str]
    metadata: Optional[dict[str, Any]]


class ImageGenerationResult(Protocol):
    images: list[GeneratedImageAsset]
    model: Optional[str]
    metadata: Optional[dict[str, Any]]


class ImageGenerationProviderConfiguredContext(Protocol):
    cfg: Any
    agent_dir: Optional[str]


class ImageGenerationModeCapabilities(Protocol):
    max_count: Optional[int]
    supports_size: Optional[bool]
    supports_aspect_ratio: Optional[bool]
    supports_resolution: Optional[bool]


class ImageGenerationEditCapabilities(ImageGenerationModeCapabilities, Protocol):
    enabled: bool
    max_input_images: Optional[int]
    max_input_images_by_model: Optional[dict[str, int]]
    max_input_images_by_model_prefix: Optional[dict[str, int]]


class ImageGenerationGeometryCapabilities(Protocol):
    sizes: Optional[list[str]]
    sizes_by_model: Optional[dict[str, list[str]]]
    aspect_ratios: Optional[list[str]]
    aspect_ratios_by_model: Optional[dict[str, list[str]]]
    resolutions: Optional[list[ImageGenerationResolution]]
    resolutions_by_model: Optional[dict[str, list[ImageGenerationResolution]]]


class ImageGenerationOutputCapabilities(Protocol):
    qualities: Optional[list[ImageGenerationQuality]]
    formats: Optional[list[ImageGenerationOutputFormat]]
    backgrounds: Optional[list[ImageGenerationBackground]]


class ImageGenerationProviderCapabilities(Protocol):
    generate: ImageGenerationModeCapabilities
    edit: ImageGenerationEditCapabilities
    geometry: Optional[ImageGenerationGeometryCapabilities]
    output: Optional[ImageGenerationOutputCapabilities]


class ImageGenerationProvider(Protocol):
    id: str
    aliases: Optional[list[str]]
    label: Optional[str]
    default_model: Optional[str]
    default_timeout_ms: Optional[int]
    models: Optional[list[str]]
    capabilities: ImageGenerationProviderCapabilities

    def is_configured(self, ctx: ImageGenerationProviderConfiguredContext) -> bool: ...

    async def generate_image(self, req: ImageGenerationRequest) -> ImageGenerationResult: ...
