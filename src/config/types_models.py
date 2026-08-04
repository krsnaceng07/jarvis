"""jarvis.config.types_models — model selection and provider configuration types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.models.ts``.

Focused minimal port: TypedDict shapes + the public ``MODEL_APIS`` /
``MODEL_THINKING_FORMATS`` constants and the ``is_model_thinking_format``
runtime guard. Heavy LLM/agent-runtime surface is delegated to the LLM
client and provider-runtime subsystems.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Provider API adapter ids accepted by model/provider config and schema generation.
MODEL_APIS = (
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


#: Model API id literal.
ModelApi = Literal[
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


#: Thinking/reasoning payload dialects emitted by OpenAI-compatible providers.
MODEL_THINKING_FORMATS = (
    "openai",
    "openrouter",
    "deepseek",
    "together",
    "qwen",
    "qwen-chat-template",
    "zai",
)


#: Supported thinking format string.
SupportedThinkingFormat = Literal[
    "openai", "openrouter", "deepseek", "together", "qwen", "qwen-chat-template", "zai",
]


#: Runtime guard for config-provided thinking format strings.
def is_model_thinking_format(value: str) -> bool:
    """Return whether ``value`` is one of the supported thinking-format strings."""
    return value in MODEL_THINKING_FORMATS


class ModelCompatConfig(TypedDict, total=False):
    """Provider/model compatibility switches consumed by request builders and tool schema adapters."""
    thinkingFormat: str  # SupportedThinkingFormat
    supportedReasoningEfforts: list
    reasoningEffortMap: dict
    visibleReasoningDetailTypes: list
    supportsTools: bool
    supportsPromptCacheKey: bool
    requiresStringContent: bool
    strictMessageKeys: bool
    toolSchemaProfile: str
    unsupportedToolSchemaKeywords: list
    nativeWebSearchTool: bool
    toolCallArgumentsEncoding: str
    requiresMistralToolIds: bool
    requiresOpenAiAnthropicToolPayload: bool
    # OpenAI compat fields (subset)
    supportsStore: bool
    supportsDeveloperRole: bool
    supportsReasoningEffort: bool
    supportsUsageInStreaming: bool
    supportsStrictMode: bool
    maxTokensField: str
    requiresToolResultName: bool
    requiresAssistantAfterToolResult: bool
    requiresThinkingAsText: bool
    requiresReasoningContentOnAssistantMessages: bool
    openRouterRouting: bool
    vercelGatewayRouting: bool
    zaiToolStream: bool
    cacheControlFormat: str
    sendSessionAffinityHeaders: bool
    supportsLongCacheRetention: bool
    # OpenAI responses compat
    sendSessionIdHeader: bool
    supportsTemperature: bool
    # Anthropic messages compat
    supportsEagerToolInputStreaming: bool


class ModelImageInputConfig(TypedDict, total=False):
    """Image input limits and accounting hints for a model."""
    maxBytes: int
    maxPixels: int
    maxSidePx: int
    preferredSidePx: int
    tokenMode: str  # "tile" | "detail" | "provider"


class ModelMediaInputConfig(TypedDict, total=False):
    image: ModelImageInputConfig


#: Authentication mode expected by a configured model provider.
ModelProviderAuthMode = Literal["api-key", "aws-sdk", "oauth", "token"]


class ModelProviderLocalServiceConfig(TypedDict, total=False):
    """Local service configuration for a model provider."""
    command: str
    args: list
    cwd: str
    env: dict
    healthUrl: str
    readyTimeoutMs: int
    idleStopMs: int


class TieredPricingConfig(TypedDict, total=False):
    input: float
    output: float
    cacheRead: float
    cacheWrite: float
    range: list  # [start, end) | [start]


class ModelCostConfig(TypedDict, total=False):
    """Token pricing in USD per million tokens."""
    input: float
    output: float
    cacheRead: float
    cacheWrite: float
    tieredPricing: list  # TieredPricingConfig[]


class ModelDefinitionConfig(TypedDict, total=False):
    """Catalog entry for a single model exposed by a provider."""
    id: str
    name: str
    api: str  # ModelApi
    baseUrl: str
    reasoning: bool
    input: list  # Array<"text" | "image" | "video" | "audio">
    cost: ModelCostConfig
    contextWindow: int
    contextTokens: int
    maxTokens: int
    thinkingLevelMap: dict
    params: dict
    agentRuntime: dict
    headers: dict
    compat: ModelCompatConfig
    mediaInput: ModelMediaInputConfig
    metadataSource: str  # "models-add"


class ModelProviderConfig(TypedDict, total=False):
    """Provider catalog declaration."""
    baseUrl: str
    apiKey: object  # SecretInput
    auth: str  # ModelProviderAuthMode
    api: str  # ModelApi
    contextWindow: int
    contextTokens: int
    maxTokens: int
    timeoutSeconds: int
    region: str
    injectNumCtxForOpenAICompat: bool
    params: dict
    agentRuntime: dict
    localService: ModelProviderLocalServiceConfig
    headers: dict
    authHeader: bool
    request: dict  # ConfiguredModelProviderRequest
    models: list  # ModelDefinitionConfig[]


#: Fully materialized provider declaration emitted by provider catalog plugins.
ModelProviderDeclarationConfig = ModelProviderConfig


#: User config input shape before provider defaults/models are materialized.
ModelProviderConfigInput = dict  # Partial<ModelProviderConfig>


class BedrockDiscoveryConfig(TypedDict, total=False):
    """AWS Bedrock model discovery config."""
    enabled: bool
    region: str
    providerFilter: list
    refreshInterval: int
    defaultContextWindow: int
    defaultMaxTokens: int


class DiscoveryToggleConfig(TypedDict, total=False):
    """Enables the named discovery source."""
    enabled: bool


class ModelPricingConfig(TypedDict, total=False):
    """Pricing enrichment settings."""
    enabled: bool


class ModelsConfig(TypedDict, total=False):
    """Top-level models config."""
    mode: str  # "merge" | "replace"
    providers: dict
    pricing: ModelPricingConfig


#: Top-level models config input before provider entries are normalized.
ModelsConfigInput = dict


__all__ = [
    "MODEL_APIS",
    "ModelApi",
    "MODEL_THINKING_FORMATS",
    "SupportedThinkingFormat",
    "is_model_thinking_format",
    "ModelCompatConfig",
    "ModelImageInputConfig",
    "ModelMediaInputConfig",
    "ModelProviderAuthMode",
    "ModelProviderLocalServiceConfig",
    "TieredPricingConfig",
    "ModelCostConfig",
    "ModelDefinitionConfig",
    "ModelProviderConfig",
    "ModelProviderDeclarationConfig",
    "ModelProviderConfigInput",
    "BedrockDiscoveryConfig",
    "DiscoveryToggleConfig",
    "ModelPricingConfig",
    "ModelsConfig",
    "ModelsConfigInput",
]
