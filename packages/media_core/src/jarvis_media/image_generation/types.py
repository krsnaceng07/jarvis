"""
Shared image-generation request, provider, capability, and result contracts.
Mirrors openclaw's image-generation/types.ts and runtime-types.ts.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional, Any, Protocol

ImageGenerationResolution = Literal["1K", "2K", "4K"]
ImageGenerationQuality = Literal["low", "medium", "high", "auto"]
ImageGenerationOutputFormat = Literal["png", "jpeg", "webp"]
ImageGenerationBackground = Literal["transparent", "opaque", "auto"]
ImageGenerationOpenAIModeration = Literal["low", "auto"]


@dataclass
class GeneratedImageAsset:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    revised_prompt: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ImageGenerationOpenAIOptions:
    background: Optional[ImageGenerationBackground] = None
    moderation: Optional[ImageGenerationOpenAIModeration] = None
    output_compression: Optional[float] = None
    user: Optional[str] = None


@dataclass
class ImageGenerationProviderOptions:
    openai: Optional[ImageGenerationOpenAIOptions] = None
    raw: dict[str, Any] = field(default_factory=dict)


ImageGenerationIgnoredOverrideKey = Literal[
    "size",
    "aspectRatio",
    "resolution",
    "quality",
    "outputFormat",
    "background",
]


@dataclass
class ImageGenerationIgnoredOverride:
    key: ImageGenerationIgnoredOverrideKey
    value: str


@dataclass
class ImageGenerationSourceImage:
    buffer: bytes
    mime_type: str
    file_name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ImageGenerationProviderConfiguredContext:
    cfg: Any  # OpenClawConfig equivalent
    agent_dir: Optional[str] = None


@dataclass
class ImageGenerationRequest:
    provider: str
    model: str
    prompt: str
    cfg: Any
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    timeout_ms: Optional[int] = None
    count: Optional[int] = None
    size: Optional[str] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[ImageGenerationResolution] = None
    quality: Optional[ImageGenerationQuality] = None
    output_format: Optional[ImageGenerationOutputFormat] = None
    background: Optional[ImageGenerationBackground] = None
    input_images: Optional[list[ImageGenerationSourceImage]] = None
    provider_options: Optional[ImageGenerationProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class ImageGenerationResult:
    images: list[GeneratedImageAsset]
    model: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ImageGenerationModeCapabilities:
    max_count: Optional[int] = None
    supports_size: Optional[bool] = None
    supports_aspect_ratio: Optional[bool] = None
    supports_resolution: Optional[bool] = None


@dataclass
class ImageGenerationEditCapabilities(ImageGenerationModeCapabilities):
    enabled: bool = False
    max_input_images: Optional[int] = None
    max_input_images_by_model: Optional[dict[str, int]] = None
    max_input_images_by_model_prefix: Optional[dict[str, int]] = None


@dataclass
class ImageGenerationGeometryCapabilities:
    sizes: Optional[list[str]] = None
    sizes_by_model: Optional[dict[str, list[str]]] = None
    aspect_ratios: Optional[list[str]] = None
    aspect_ratios_by_model: Optional[dict[str, list[str]]] = None
    resolutions: Optional[list[ImageGenerationResolution]] = None
    resolutions_by_model: Optional[dict[str, list[ImageGenerationResolution]]] = None


@dataclass
class ImageGenerationOutputCapabilities:
    qualities: Optional[list[ImageGenerationQuality]] = None
    formats: Optional[list[ImageGenerationOutputFormat]] = None
    backgrounds: Optional[list[ImageGenerationBackground]] = None


@dataclass
class MediaNormalizationEntry:
    applied: Any
    derived_from: Optional[str] = None


@dataclass
class ImageGenerationNormalization:
    size: Optional[MediaNormalizationEntry] = None
    aspect_ratio: Optional[MediaNormalizationEntry] = None
    resolution: Optional[MediaNormalizationEntry] = None


@dataclass
class ImageGenerationProviderCapabilities:
    generate: ImageGenerationModeCapabilities
    edit: ImageGenerationEditCapabilities
    geometry: Optional[ImageGenerationGeometryCapabilities] = None
    output: Optional[ImageGenerationOutputCapabilities] = None


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


@dataclass
class GenerateImageParams:
    cfg: Any
    prompt: str
    agent_dir: Optional[str] = None
    auth_store: Optional[Any] = None
    model_override: Optional[str] = None
    count: Optional[int] = None
    size: Optional[str] = None
    aspect_ratio: Optional[str] = None
    resolution: Optional[ImageGenerationResolution] = None
    inferred_resolution: Optional[ImageGenerationResolution] = None
    quality: Optional[ImageGenerationQuality] = None
    output_format: Optional[ImageGenerationOutputFormat] = None
    background: Optional[ImageGenerationBackground] = None
    input_images: Optional[list[ImageGenerationSourceImage]] = None
    auto_provider_fallback: Optional[bool] = None
    timeout_ms: Optional[int] = None
    provider_options: Optional[ImageGenerationProviderOptions] = None
    ssrf_policy: Optional[Any] = None


@dataclass
class FallbackAttempt:
    provider: str
    model: str
    error: str
    reason: Optional[str] = None
    status: Optional[int] = None
    code: Optional[str] = None


@dataclass
class GenerateImageRuntimeResult:
    images: list[GeneratedImageAsset]
    provider: str
    model: str
    attempts: list[FallbackAttempt]
    applied_resolution: Optional[ImageGenerationResolution] = None
    normalization: Optional[ImageGenerationNormalization] = None
    metadata: Optional[dict[str, Any]] = None
    ignored_overrides: list[ImageGenerationIgnoredOverride] = field(default_factory=list)
