"""jarvis.config.types_base — base configuration types shared by multiple sections.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.base.ts``.

Focused minimal port: Literal unions, TypedDict shapes, and the
:data:`IdentityConfig` / :data:`SessionConfig` / :data:`LoggingConfig` /
:data:`AuditConfig` / :data:`DiagnosticsConfig` / :data:`WebConfig`
record shapes. Cross-references to other types are preserved as
:data:`dict` aliases since the Python port already exposes the canonical
shapes via sibling modules.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Reply handling mode for chat command surfaces.
ReplyMode = Literal["text", "command"]

#: Typing indicator timing policy shared by channel configs.
TypingMode = Literal["never", "instant", "thinking", "message"]

#: Session-key ownership model for inbound messages.
SessionScope = Literal["per-sender", "global"]

#: DM session-key granularity across peers, channels, and accounts.
DmScope = Literal["main", "per-peer", "per-channel-peer", "per-account-channel-peer"]

#: Which source messages outbound replies should thread or quote against.
ReplyToMode = Literal["off", "first", "all", "batched"]

#: Group-chat admission policy for channels with allowlists.
GroupPolicy = Literal["open", "disabled", "allowlist"]

#: Direct-message admission policy for channels with pairing/allowlists.
DmPolicy = Literal["pairing", "allowlist", "open", "disabled"]

#: How much non-allowlisted context is visible to an agent.
ContextVisibilityMode = Literal["all", "allowlist", "allowlist_quote"]

#: Text splitting strategy for outbound channel delivery.
TextChunkMode = Literal["length", "newline"]

#: Preview/progress delivery mode while an agent response is still streaming.
StreamingMode = Literal["off", "partial", "block", "progress"]

#: How command text is represented in streaming progress previews.
ChannelStreamingCommandTextMode = Literal["raw", "status"]


class OutboundRetryConfig(TypedDict, total=False):
    """Outbound request retry policy."""
    attempts: int
    minDelayMs: int
    maxDelayMs: int
    jitter: float


class BlockStreamingCoalesceConfig(TypedDict, total=False):
    """Coalesce settings for block-mode streaming."""
    minChars: int
    maxChars: int
    idleMs: int


class BlockStreamingChunkConfig(TypedDict, total=False):
    """Chunk thresholds for block streaming."""
    minChars: int
    maxChars: int
    breakPreference: str  # "paragraph" | "newline" | "sentence"


class ChannelStreamingProgressConfig(TypedDict, total=False):
    """Progress-mode streaming config."""
    label: object  # str | false
    labels: list
    maxLines: int
    maxLineChars: int
    render: str  # "text" | "rich"
    toolProgress: bool
    commandText: str  # ChannelStreamingCommandTextMode
    commentary: bool
    narration: bool


class ChannelStreamingPreviewConfig(TypedDict, total=False):
    """Preview streaming config."""
    chunk: BlockStreamingChunkConfig
    toolProgress: bool
    commandText: str  # ChannelStreamingCommandTextMode


class ChannelStreamingBlockConfig(TypedDict, total=False):
    """Block streaming config."""
    enabled: bool
    coalesce: BlockStreamingCoalesceConfig


class ChannelStreamingConfig(TypedDict, total=False):
    """Top-level channel streaming config."""
    mode: str  # StreamingMode
    chunkMode: str  # TextChunkMode
    nativeTransport: bool
    preview: ChannelStreamingPreviewConfig
    progress: ChannelStreamingProgressConfig
    block: ChannelStreamingBlockConfig


#: Streaming subset used by channels that only consume chunk + block delivery.
ChannelDeliveryStreamingConfig = dict  # Pick<ChannelStreamingConfig, "chunkMode" | "block">


#: Streaming subset used by channels that render visible preview/progress replies.
ChannelPreviewStreamingConfig = dict  # Pick<ChannelStreamingConfig, "mode" | "chunkMode" | "preview" | "progress" | "block">


#: Markdown table rendering mode.
MarkdownTableMode = Literal["off", "bullets", "code", "block"]


class MarkdownConfig(TypedDict, total=False):
    """Markdown formatting overrides."""
    tables: str  # MarkdownTableMode


class HumanDelayConfig(TypedDict, total=False):
    """Human-like delay between block replies."""
    mode: str  # "off" | "natural" | "custom"
    minMs: int
    maxMs: int


#: Session send-policy rule action.
SessionSendPolicyAction = Literal["allow", "deny"]


class SessionSendPolicyMatch(TypedDict, total=False):
    """Session send-policy match filter."""
    channel: str
    chatType: str  # ChatType
    keyPrefix: str
    rawKeyPrefix: str


class SessionSendPolicyRule(TypedDict, total=False):
    """Session send-policy rule."""
    action: str  # SessionSendPolicyAction
    match: SessionSendPolicyMatch


class SessionSendPolicyConfig(TypedDict, total=False):
    """Session send-policy config."""
    default: str  # SessionSendPolicyAction
    rules: list  # SessionSendPolicyRule[]


#: Session reset trigger mode.
SessionResetMode = Literal["none", "daily", "idle"]


class SessionResetConfig(TypedDict, total=False):
    """Session reset policy."""
    mode: str  # SessionResetMode
    atHour: int
    idleMinutes: int


class SessionResetByTypeConfig(TypedDict, total=False):
    """Per-chat-type session reset policy."""
    direct: SessionResetConfig
    dm: SessionResetConfig  # deprecated
    group: SessionResetConfig
    thread: SessionResetConfig


class SessionThreadBindingsConfig(TypedDict, total=False):
    """Shared thread-bindings default config."""
    enabled: bool
    idleHours: int
    maxAgeHours: int
    spawnSessions: bool
    defaultSpawnContext: str  # "isolated" | "fork"


class SessionWriteLockConfig(TypedDict, total=False):
    """Session transcript write-lock acquisition policy."""
    acquireTimeoutMs: int
    staleMs: int
    maxHoldMs: int


#: Session-store maintenance mode.
SessionMaintenanceMode = Literal["enforce", "warn"]


class SessionMaintenanceConfig(TypedDict, total=False):
    """Session-store cleanup policy."""
    mode: str  # SessionMaintenanceMode
    pruneAfter: object  # str | number
    pruneDays: int  # deprecated
    maxEntries: int
    resetArchiveRetention: object  # str | number | false
    maxDiskBytes: object  # number | string | false
    highWaterBytes: object  # number | string


class AgentToAgentConfig(TypedDict, total=False):
    """Agent-to-agent loop config."""
    maxPingPongTurns: int


class SessionConfig(TypedDict, total=False):
    """Top-level session config."""
    scope: str  # SessionScope
    dmScope: str  # DmScope
    identityLinks: dict
    resetTriggers: list
    idleMinutes: int
    reset: SessionResetConfig
    resetByType: SessionResetByTypeConfig
    resetByChannel: dict
    store: str
    typingIntervalSeconds: int
    typingMode: str  # TypingMode
    mainKey: str
    sendPolicy: SessionSendPolicyConfig
    writeLock: SessionWriteLockConfig
    agentToAgent: AgentToAgentConfig
    threadBindings: SessionThreadBindingsConfig
    maintenance: SessionMaintenanceConfig


#: Logging level.
LogLevel = Literal["silent", "fatal", "error", "warn", "info", "debug", "trace"]


class LoggingConfig(TypedDict, total=False):
    """Logging config."""
    level: str  # LogLevel
    file: str
    maxFileBytes: int
    consoleLevel: str  # LogLevel
    consoleStyle: str  # "pretty" | "compact" | "json"
    redactSensitive: str  # "off" | "tools"
    redactPatterns: list  # string[]


class DiagnosticsOtelConfig(TypedDict, total=False):
    """OTEL diagnostics config."""
    enabled: bool
    endpoint: str
    tracesEndpoint: str
    metricsEndpoint: str
    logsEndpoint: str
    protocol: str  # "http/protobuf" | "grpc"
    headers: dict
    serviceName: str
    traces: bool
    metrics: bool
    logs: bool
    logsExporter: str  # "otlp" | "stdout" | "both"
    sampleRate: float
    flushIntervalMs: int
    captureContent: object  # bool | captureContentObject


class DiagnosticsCacheTraceConfig(TypedDict, total=False):
    """Cache-trace diagnostic config."""
    enabled: bool
    filePath: str
    includeMessages: bool
    includePrompt: bool
    includeSystem: bool


class AuditConfig(TypedDict, total=False):
    """Audit logging config."""
    enabled: bool
    messages: str  # "off" | "direct" | "all"


class DiagnosticsConfig(TypedDict, total=False):
    """Diagnostics config."""
    enabled: bool
    flags: list
    stuckSessionWarnMs: int
    stuckSessionAbortMs: int
    memoryPressureSnapshot: bool
    otel: DiagnosticsOtelConfig
    cacheTrace: DiagnosticsCacheTraceConfig


class WebReconnectConfig(TypedDict, total=False):
    """Web provider reconnect config."""
    initialMs: int
    maxMs: int
    factor: float
    jitter: float
    maxAttempts: int


class WebWhatsAppConfig(TypedDict, total=False):
    """Web WhatsApp transport config."""
    keepAliveIntervalMs: int
    connectTimeoutMs: int
    defaultQueryTimeoutMs: int


class WebConfig(TypedDict, total=False):
    """Web (WhatsApp-web) provider config."""
    enabled: bool
    heartbeatSeconds: int
    reconnect: WebReconnectConfig
    whatsapp: WebWhatsAppConfig


#: Provider docking allowlist keyed by provider id.
AgentElevatedAllowFromConfig = dict  # Partial<Record<string, Array<string | number>>>


class IdentityConfig(TypedDict, total=False):
    """Agent identity config."""
    name: str
    theme: str
    emoji: str
    avatar: str


__all__ = [
    "ReplyMode",
    "TypingMode",
    "SessionScope",
    "DmScope",
    "ReplyToMode",
    "GroupPolicy",
    "DmPolicy",
    "ContextVisibilityMode",
    "TextChunkMode",
    "StreamingMode",
    "ChannelStreamingCommandTextMode",
    "OutboundRetryConfig",
    "BlockStreamingCoalesceConfig",
    "BlockStreamingChunkConfig",
    "ChannelStreamingProgressConfig",
    "ChannelStreamingPreviewConfig",
    "ChannelStreamingBlockConfig",
    "ChannelStreamingConfig",
    "ChannelDeliveryStreamingConfig",
    "ChannelPreviewStreamingConfig",
    "MarkdownTableMode",
    "MarkdownConfig",
    "HumanDelayConfig",
    "SessionSendPolicyAction",
    "SessionSendPolicyMatch",
    "SessionSendPolicyRule",
    "SessionSendPolicyConfig",
    "SessionResetMode",
    "SessionResetConfig",
    "SessionResetByTypeConfig",
    "SessionThreadBindingsConfig",
    "SessionWriteLockConfig",
    "SessionMaintenanceMode",
    "SessionMaintenanceConfig",
    "AgentToAgentConfig",
    "SessionConfig",
    "LogLevel",
    "LoggingConfig",
    "DiagnosticsOtelConfig",
    "DiagnosticsCacheTraceConfig",
    "AuditConfig",
    "DiagnosticsConfig",
    "WebReconnectConfig",
    "WebWhatsAppConfig",
    "WebConfig",
    "AgentElevatedAllowFromConfig",
    "IdentityConfig",
]
