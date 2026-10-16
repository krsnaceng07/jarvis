"""Shared model-catalog data contracts for manifests and normalized rows.

OpenClaw parity: ``packages/model-catalog-core/src/model-catalog-types.ts``.
These are plain frozen dataclasses (parity for the TS structural types);
remote-bundle validation lives in :mod:`remote_catalog_bundle`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

#: Supported API protocols for model catalog entries.
MODEL_CATALOG_APIS: tuple[str, ...] = (
    "openai-completions",
    "openai-responses",
    "openai-chatgpt-responses",
    "anthropic-messages",
    "google-generative-ai",
    "google-vertex",
    "github-copilot",
    "bedrock-converse-stream",
    "ollama",
    "azure-openai-responses",
)

ModelCatalogApi = Literal[
    "openai-completions",
    "openai-responses",
    "openai-chatgpt-responses",
    "anthropic-messages",
    "google-generative-ai",
    "google-vertex",
    "github-copilot",
    "bedrock-converse-stream",
    "ollama",
    "azure-openai-responses",
]

#: Supported model thinking/reasoning wire formats.
MODEL_CATALOG_THINKING_FORMATS: tuple[str, ...] = (
    "openai",
    "openrouter",
    "deepseek",
    "together",
    "qwen",
    "qwen-chat-template",
    "zai",
)

ModelCatalogThinkingFormat = Literal[
    "openai",
    "openrouter",
    "deepseek",
    "together",
    "qwen",
    "qwen-chat-template",
    "zai",
]


def is_model_catalog_thinking_format(value: str) -> bool:
    """Narrow a string to a supported thinking wire format."""
    return value in MODEL_CATALOG_THINKING_FORMATS


#: Model-level thinking levels carried by provider catalog metadata.
MODEL_CATALOG_THINKING_LEVELS: tuple[str, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

ModelCatalogThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"]
ModelCatalogThinkingLevelMap = dict[ModelCatalogThinkingLevel, str | None]

ModelCatalogDiscovery = Literal["static", "refreshable", "runtime"]
ModelCatalogStatus = Literal["available", "preview", "deprecated", "disabled"]
ModelCatalogSource = Literal["manifest", "provider-index", "cache", "config", "runtime-refresh"]
ModelCatalogInput = Literal["text", "image", "document"]

UnifiedModelCatalogKind = Literal[
    "text", "voice", "image_generation", "video_generation", "music_generation"
]
UnifiedModelCatalogSource = Literal[
    "manifest", "provider-index", "static", "live", "cache", "configured", "runtime-refresh"
]

#: Hard bound on provider-declared context-window choices per model.
MODEL_CATALOG_MAX_CONTEXT_WINDOWS = 16


@dataclass(frozen=True, slots=True)
class ModelCatalogOpenRouterRouting:
    """OpenRouter routing preferences copied into request metadata."""

    allow_fallbacks: bool | None = None
    require_parameters: bool | None = None
    data_collection: Literal["deny", "allow"] | None = None
    zdr: bool | None = None
    enforce_distillable_text: bool | None = None
    order: tuple[str, ...] = field(default_factory=tuple)
    only: tuple[str, ...] = field(default_factory=tuple)
    ignore: tuple[str, ...] = field(default_factory=tuple)
    quantizations: tuple[str, ...] = field(default_factory=tuple)
    sort: str | dict[str, Any] | None = None
    max_price: dict[str, float | str] | None = None
    preferred_min_throughput: float | dict[str, float] | None = None
    preferred_max_latency: float | dict[str, float] | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogVercelGatewayRouting:
    """Vercel AI Gateway routing preferences."""

    only: tuple[str, ...] = field(default_factory=tuple)
    order: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ModelCatalogImageInputConfig:
    """Image input limits for a model."""

    max_bytes: int | None = None
    max_pixels: int | None = None
    max_side_px: int | None = None
    preferred_side_px: int | None = None
    token_mode: Literal["tile", "detail", "provider"] | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogMediaInputConfig:
    """Media input limits for a model."""

    image: ModelCatalogImageInputConfig | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogCompatConfig:
    """Compatibility flags and provider-specific routing metadata for one model."""

    supports_store: bool | None = None
    supports_developer_role: bool | None = None
    supports_reasoning_effort: bool | None = None
    # Whether the model accepts temperature (GPT-5.6 family rejects it).
    supports_temperature: bool | None = None
    # Whether the provider honors top-level `instructions` on Responses requests.
    supports_instructions: bool | None = None
    supports_usage_in_streaming: bool | None = None
    supports_strict_mode: bool | None = None
    supports_json_schema_response_format: bool | None = None
    max_tokens_field: Literal["max_completion_tokens", "max_tokens"] | None = None
    requires_tool_result_name: bool | None = None
    requires_assistant_after_tool_result: bool | None = None
    requires_thinking_as_text: bool | None = None
    requires_reasoning_content_on_assistant_messages: bool | None = None
    open_router_routing: ModelCatalogOpenRouterRouting | None = None
    vercel_gateway_routing: ModelCatalogVercelGatewayRouting | None = None
    zai_tool_stream: bool | None = None
    cache_control_format: Literal["anthropic"] | None = None
    send_session_affinity_headers: bool | None = None
    send_session_id_header: bool | None = None
    supports_eager_tool_input_streaming: bool | None = None
    supports_long_cache_retention: bool | None = None
    supports_prompt_cache_key: bool | None = None
    supports_tools: bool | None = None
    # Code-mode tier for `tools.codeMode.enabled: "auto"`; absent means "capable".
    code_mode: Literal["preferred", "capable"] | None = None
    requires_string_content: bool | None = None
    strict_message_keys: bool | None = None
    tool_schema_profile: str | None = None
    unsupported_tool_schema_keywords: tuple[str, ...] = field(default_factory=tuple)
    tool_call_arguments_encoding: str | None = None
    requires_openai_anthropic_tool_payload: bool | None = None
    thinking_format: ModelCatalogThinkingFormat | None = None
    supported_reasoning_efforts: tuple[str, ...] = field(default_factory=tuple)
    reasoning_effort_map: dict[str, str] = field(default_factory=dict)
    visible_reasoning_detail_types: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ModelCatalogTieredCost:
    """Tiered token cost row."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0
    cost_range: tuple[float, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ModelCatalogCost:
    """Token cost metadata for one model."""

    input: float | None = None
    output: float | None = None
    cache_read: float | None = None
    cache_write: float | None = None
    tiered_pricing: tuple[ModelCatalogTieredCost, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ModelCatalogContextWindowOption:
    """Bounded provider-declared context-window choice for one model."""

    id: str = ""
    label: str = ""
    context_window: int = 0


@dataclass(frozen=True, slots=True)
class ModelCatalogModel:
    """Provider manifest model entry."""

    id: str = ""
    name: str | None = None
    api: ModelCatalogApi | None = None
    base_url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    input: tuple[ModelCatalogInput, ...] = field(default_factory=tuple)
    reasoning: bool | None = None
    context_window: float | None = None
    context_windows: tuple[ModelCatalogContextWindowOption, ...] = field(default_factory=tuple)
    context_window_default: str | None = None
    context_tokens: float | None = None
    max_tokens: float | None = None
    thinking_level_map: dict[str, str | None] = field(default_factory=dict)
    cost: ModelCatalogCost | None = None
    compat: ModelCatalogCompatConfig | None = None
    # Authoring metadata only: normalization drops it. Keeps `compat`
    # capability tiers from drifting apart for shared upstream models.
    upstream_model: str | None = None
    media_input: ModelCatalogMediaInputConfig | None = None
    status: ModelCatalogStatus | None = None
    status_reason: str | None = None
    replaces: tuple[str, ...] = field(default_factory=tuple)
    replaced_by: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ModelCatalogProvider:
    """Provider manifest catalog entry."""

    models: tuple[ModelCatalogModel, ...] = field(default_factory=tuple)
    base_url: str | None = None
    api: ModelCatalogApi | None = None
    headers: dict[str, str] = field(default_factory=dict)
    default_model: str | None = None
    default_utility_model: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogAlias:
    """Provider alias entry."""

    provider: str = ""
    api: ModelCatalogApi | None = None
    base_url: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogSuppressionRetirement:
    """Explicit retirement with an optional provider-local successor."""

    replaced_by: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalogSuppressionWhen:
    """Config scope limiting when a suppression applies."""

    base_url_hosts: tuple[str, ...] = field(default_factory=tuple)
    provider_config_api_in: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ModelCatalogSuppression:
    """Suppression rule hiding a provider/model under matching config."""

    provider: str = ""
    model: str = ""
    reason: str | None = None
    retirement: ModelCatalogSuppressionRetirement | None = None
    when: ModelCatalogSuppressionWhen | None = None


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    """Raw model catalog manifest shape."""

    providers: dict[str, ModelCatalogProvider] = field(default_factory=dict)
    aliases: dict[str, ModelCatalogAlias] = field(default_factory=dict)
    suppressions: tuple[ModelCatalogSuppression, ...] = field(default_factory=tuple)
    discovery: dict[str, ModelCatalogDiscovery] = field(default_factory=dict)
    models_dev: dict[str, str] = field(default_factory=dict)
    runtime_augment: bool | None = None


@dataclass(frozen=True, slots=True)
class NormalizedModelCatalogRow(ModelCatalogModel):
    """Normalized catalog row used by runtime lookup and UI surfaces.

    Extends the model snapshot with join identity (``ref``/``merge_key``),
    resolved defaults (``name``/``input``/``reasoning``/``status``), and
    provider-level fallbacks (``api``/``base_url``/``headers``).
    """

    provider: str = ""
    ref: str = ""
    merge_key: str = ""
    source: ModelCatalogSource = "manifest"


@dataclass(frozen=True, slots=True)
class UnifiedModelCatalogEntry:
    """Unified catalog entry for provider/model pickers."""

    kind: UnifiedModelCatalogKind = "text"
    provider: str = ""
    model: str = ""
    source: UnifiedModelCatalogSource = "manifest"
    label: str | None = None
    default: bool = False
    configured: bool = False
    capabilities: Any | None = None
    modes: tuple[str, ...] = field(default_factory=tuple)
    auth_env_vars: tuple[str, ...] = field(default_factory=tuple)
    docs_path: str | None = None
    fetched_at: int | None = None
    expires_at: int | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "MODEL_CATALOG_APIS",
    "MODEL_CATALOG_MAX_CONTEXT_WINDOWS",
    "MODEL_CATALOG_THINKING_FORMATS",
    "MODEL_CATALOG_THINKING_LEVELS",
    "ModelCatalog",
    "ModelCatalogAlias",
    "ModelCatalogApi",
    "ModelCatalogCompatConfig",
    "ModelCatalogContextWindowOption",
    "ModelCatalogCost",
    "ModelCatalogDiscovery",
    "ModelCatalogImageInputConfig",
    "ModelCatalogInput",
    "ModelCatalogMediaInputConfig",
    "ModelCatalogModel",
    "ModelCatalogOpenRouterRouting",
    "ModelCatalogProvider",
    "ModelCatalogSource",
    "ModelCatalogStatus",
    "ModelCatalogSuppression",
    "ModelCatalogSuppressionRetirement",
    "ModelCatalogSuppressionWhen",
    "ModelCatalogThinkingFormat",
    "ModelCatalogThinkingLevel",
    "ModelCatalogThinkingLevelMap",
    "ModelCatalogTieredCost",
    "ModelCatalogVercelGatewayRouting",
    "NormalizedModelCatalogRow",
    "UnifiedModelCatalogEntry",
    "UnifiedModelCatalogKind",
    "UnifiedModelCatalogSource",
    "is_model_catalog_thinking_format",
]
