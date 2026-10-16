"""jarvis.config.types_tools — tool availability and allowlist config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.tools.ts``.

Focused minimal port: TypedDict shapes + Literal unions for the
``ToolsConfig`` family. Cross-references to other types are preserved
as :data:`dict` aliases.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Send policy action (re-exported here for tools-side reference).
ToolSendPolicyAction = Literal["allow", "deny"]


#: Media understanding scope match.
class MediaUnderstandingScopeMatch(TypedDict, total=False):
    channel: str
    chatType: str
    keyPrefix: str


class MediaUnderstandingScopeRule(TypedDict, total=False):
    action: str  # ToolSendPolicyAction
    match: MediaUnderstandingScopeMatch


class MediaUnderstandingScopeConfig(TypedDict, total=False):
    default: str  # ToolSendPolicyAction
    rules: list  # MediaUnderstandingScopeRule[]


#: Media understanding capability.
MediaUnderstandingCapability = Literal["image", "audio", "video"]


#: Media understanding attachment mode.
MediaUnderstandingAttachmentMode = Literal["first", "all"]


#: Media understanding attachment preference.
MediaUnderstandingAttachmentPrefer = Literal["first", "last", "path", "url"]


class MediaUnderstandingAttachmentsConfig(TypedDict, total=False):
    mode: str
    maxAttachments: int
    prefer: str


class MediaProviderRequestConfig(TypedDict, total=False):
    """Common provider-request overrides for media understanding."""
    providerOptions: dict
    deepgram: dict
    baseUrl: str
    headers: dict
    request: dict


class MediaUnderstandingModelConfig(TypedDict, total=False):
    """Single media-understanding model entry."""
    provider: str
    model: str
    capabilities: list
    type: str
    command: str
    args: list
    prompt: str
    maxChars: int
    maxBytes: int
    timeoutSeconds: int
    language: str
    profile: str
    preferredProfile: str
    # Inherited from MediaProviderRequestConfig
    providerOptions: dict
    baseUrl: str
    headers: dict
    request: dict


class MediaUnderstandingConfig(TypedDict, total=False):
    """Media understanding config (image/audio/video)."""
    enabled: bool
    scope: MediaUnderstandingScopeConfig
    maxBytes: int
    maxChars: int
    prompt: str
    _requestPromptOverride: str
    timeoutSeconds: int
    language: str
    _requestLanguageOverride: str
    attachments: MediaUnderstandingAttachmentsConfig
    models: list
    echoTranscript: bool
    echoFormat: str
    # Inherited from MediaProviderRequestConfig
    providerOptions: dict
    baseUrl: str
    headers: dict
    request: dict


class LinkModelConfig(TypedDict, total=False):
    """Link understanding model entry."""
    type: str
    command: str
    args: list
    timeoutSeconds: int


class LinkToolsConfig(TypedDict, total=False):
    """Link understanding config."""
    enabled: bool
    scope: MediaUnderstandingScopeConfig
    maxLinks: int
    timeoutSeconds: int
    models: list


class MediaToolsConfig(TypedDict, total=False):
    """Media tools aggregate config."""
    enabled: bool
    image: MediaUnderstandingConfig
    audio: MediaUnderstandingConfig
    video: MediaUnderstandingConfig
    link: LinkToolsConfig


#: Tool/profile profile fixture shape.
SafeBinProfileFixture = dict  # SafeBinProfileFixture (exec safe bin policy)


#: Group tool policy.
class GroupToolPolicyConfig(TypedDict, total=False):
    """Per-group/per-channel tool policy."""
    allow: list
    deny: list
    alsoAllow: list
    profile: str
    profiles: list


#: Group tool policy by sender.
class GroupToolPolicyBySenderConfig(TypedDict, total=False):
    """Sender-scoped group tool policy overrides."""
    allow: list
    deny: list
    alsoAllow: list
    profile: str
    profiles: list


#: Web search tool provider id.
WebSearchProvider = str


class WebSearchConfig(TypedDict, total=False):
    """Web search tool config."""
    enabled: bool
    provider: str  # WebSearchProvider
    apiKey: object  # SecretInput
    maxResults: int
    timeoutSeconds: int
    cacheTtlMinutes: int
    # Provider-specific fields
    providerOptions: dict


class WebFetchConfig(TypedDict, total=False):
    """Web fetch tool config."""
    enabled: bool
    maxBytes: int
    timeoutSeconds: int
    cacheTtlMinutes: int
    allowedHosts: list
    blockPrivateNetwork: bool


class WebToolsConfig(TypedDict, total=False):
    """Web tools aggregate (search + fetch)."""
    enabled: bool
    search: WebSearchConfig
    fetch: WebFetchConfig


#: Tool progress detail level.
ToolProgressDetail = Literal["off", "new-failed", "new", "all"]


#: Tool profile id (string).
ToolProfile = str


#: Tool entry config (one tool, allow/deny/profile).
class ToolEntryConfig(TypedDict, total=False):
    """Per-tool allow/deny/profile override."""
    allow: bool
    deny: bool
    alsoAllow: list
    profile: str
    profiles: list


class ExecRuntimeConfig(TypedDict, total=False):
    """Exec tool runtime config."""
    timeoutSeconds: int
    maxOutputBytes: int
    host: str  # "auto" | "sandbox" | "gateway" | "node"
    mode: str  # "deny" | "allowlist" | "ask" | "auto" | "full"
    security: str  # "deny" | "allowlist" | "full"
    ask: str  # "off" | "on-miss" | "always"
    node: str
    safeBins: list
    safeBinProfile: str
    safeBinTrustedDirs: list
    safeBinProfiles: dict  # Record<string, SafeBinProfileFixture>
    allowInsecurePath: bool
    binding: dict
    reviewer: dict  # { model?: dict }


class CodeModeConfig(TypedDict, total=False):
    """Code-mode tool config (run js/python in sandboxed runtime)."""
    enabled: bool
    timeoutSeconds: int
    maxOutputBytes: int


class ToolHeartbeatConfig(TypedDict, total=False):
    """Tool heartbeat/keep-alive config."""
    intervalMs: int
    timeoutMs: int


class ToolLoopDetectionDetectorConfig(TypedDict, total=False):
    """Tool loop detection detector toggles."""
    genericRepeat: bool
    knownPollNoProgress: bool
    pingPong: bool


class ToolLoopPostCompactionGuardConfig(TypedDict, total=False):
    """Post-compaction loop guard config."""
    windowSize: int


class ToolLoopDetectionConfig(TypedDict, total=False):
    """Tool loop-detection config."""
    enabled: bool
    historySize: int
    warningThreshold: int
    unknownToolThreshold: int
    criticalThreshold: int
    globalCircuitBreakerThreshold: int
    detectors: ToolLoopDetectionDetectorConfig
    postCompactionGuard: ToolLoopPostCompactionGuardConfig


class AgentToolsConfig(TypedDict, total=False):
    """Per-agent tool overrides."""
    allow: list
    deny: list
    alsoAllow: list
    profile: str
    profiles: list
    byProvider: dict
    progress: ToolProgressDetail
    heartbeat: ToolHeartbeatConfig
    loopDetection: ToolLoopDetectionConfig
    web: WebToolsConfig
    media: MediaToolsConfig
    exec: ExecRuntimeConfig
    codeMode: CodeModeConfig
    memorySearch: dict


class ToolsConfig(TypedDict, total=False):
    """Top-level tools config."""
    profile: str
    profiles: dict  # Record<string, ToolProfileConfig>
    allow: list
    deny: list
    alsoAllow: list
    byProvider: dict
    progress: ToolProgressDetail
    heartbeat: ToolHeartbeatConfig
    loopDetection: ToolLoopDetectionConfig
    web: WebToolsConfig
    media: MediaToolsConfig
    exec: ExecRuntimeConfig
    codeMode: CodeModeConfig
    elevatedAllowFrom: dict  # AgentElevatedAllowFromConfig


#: Tool profile config.
ToolProfileConfig = dict  # {allow?: string[], deny?: string[], alsoAllow?: string[]}


__all__ = [
    "ToolSendPolicyAction",
    "MediaUnderstandingScopeMatch",
    "MediaUnderstandingScopeRule",
    "MediaUnderstandingScopeConfig",
    "MediaUnderstandingCapability",
    "MediaUnderstandingAttachmentMode",
    "MediaUnderstandingAttachmentPrefer",
    "MediaUnderstandingAttachmentsConfig",
    "MediaProviderRequestConfig",
    "MediaUnderstandingModelConfig",
    "MediaUnderstandingConfig",
    "LinkModelConfig",
    "LinkToolsConfig",
    "MediaToolsConfig",
    "SafeBinProfileFixture",
    "GroupToolPolicyConfig",
    "GroupToolPolicyBySenderConfig",
    "WebSearchProvider",
    "WebSearchConfig",
    "WebFetchConfig",
    "WebToolsConfig",
    "ToolProgressDetail",
    "ToolProfile",
    "ToolEntryConfig",
    "ExecRuntimeConfig",
    "CodeModeConfig",
    "ToolHeartbeatConfig",
    "ToolLoopDetectionDetectorConfig",
    "ToolLoopPostCompactionGuardConfig",
    "ToolLoopDetectionConfig",
    "AgentToolsConfig",
    "ToolsConfig",
    "ToolProfileConfig",
]
