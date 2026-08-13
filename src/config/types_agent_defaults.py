"""jarvis.config.types_agent_defaults — agent default configuration types.

OpenClaw parity: mirrors
``openclaw-main/src/config/types.agent-defaults.ts``.

Focused minimal port: TypedDict shapes + Literal unions for the
``AgentDefaultsConfig`` family. Cross-references to other types
(``types.agents-shared``, ``types.base``, etc.) are preserved as
:data:`dict` aliases since the Python port already exposes the canonical
shapes via sibling modules.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Workspace bootstrap-file injection policy for agent system prompts.
AgentContextInjection = Literal["always", "continuation-skip", "never"]


#: Optional bootstrap files that setup can skip while still creating required agent files.
OptionalBootstrapFileName = Literal["SOUL.md", "USER.md", "HEARTBEAT.md", "IDENTITY.md"]


#: Embedded runner behavior contract used by strict-agentic provider flows.
EmbeddedAgentExecutionContract = Literal["default", "strict-agentic"]


#: Prompt-only default for how strongly agents should delegate to sub-agents.
SubagentDelegationMode = Literal["suggest", "prefer"]


#: Image compression/detail preference used before sending image inputs to models.
AgentImageQualityPreference = Literal["auto", "efficient", "balanced", "high"]


#: Canonical thinking levels accepted by agent defaults and compaction overrides.
AgentThinkingLevel = Literal[
    "off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max", "ultra",
]


#: GPT-5 prompt overlay personality.
Gpt5Personality = Literal["friendly", "on", "off"]


class Gpt5PromptOverlayConfig(TypedDict, total=False):
    """Friendly interaction-style layer for GPT-5-family models (default: friendly)."""
    personality: str  # Gpt5Personality


class PromptOverlaysConfig(TypedDict, total=False):
    """Provider-independent prompt overlays applied by model family."""
    gpt5: Gpt5PromptOverlayConfig


class AgentModelEntryConfig(TypedDict, total=False):
    """Per-model metadata override for a configured provider/model entry."""
    alias: str
    params: dict
    agentRuntime: dict
    streaming: bool


class AgentModelPolicyConfig(TypedDict, total=False):
    """Explicit model override policy. Empty or omitted allow permits any model."""
    allow: list


class AgentModelListConfig(TypedDict, total=False):
    """Primary model and fallbacks."""
    primary: str
    fallbacks: list


#: Agent context-pruning mode.
AgentContextPruningMode = Literal["off", "cache-ttl"]


class AgentContextPruningToolsConfig(TypedDict, total=False):
    """Tool allow/deny for context pruning."""
    allow: list
    deny: list


class AgentContextPruningSoftTrimConfig(TypedDict, total=False):
    """Soft trim parameters."""
    maxChars: int
    headChars: int
    tailChars: int


class AgentContextPruningHardClearConfig(TypedDict, total=False):
    """Hard clear parameters."""
    enabled: bool
    placeholder: str


class AgentContextPruningConfig(TypedDict, total=False):
    """Pruning policy for old tool results in model context."""
    mode: str  # AgentContextPruningMode
    ttl: str
    keepLastAssistants: int
    softTrimRatio: float
    hardClearRatio: float
    minPrunableToolChars: int
    tools: AgentContextPruningToolsConfig
    softTrim: AgentContextPruningSoftTrimConfig
    hardClear: AgentContextPruningHardClearConfig


class AgentStartupContextConfig(TypedDict, total=False):
    """Runtime-owned startup-context prelude on bare session resets."""
    enabled: bool
    applyOn: list
    dailyMemoryDays: int
    maxFileBytes: int
    maxFileChars: int
    maxTotalChars: int


class AgentContextLimitsConfig(TypedDict, total=False):
    """Per-agent context/token-heavy limits."""
    memoryGetMaxChars: int
    memoryGetDefaultLines: int
    toolResultMaxChars: int
    postCompactionMaxChars: int


class AgentRunRetriesConfig(TypedDict, total=False):
    """Outer run-loop retry boundaries."""
    base: int
    perProfile: int
    min: int
    max: int


#: CliBackend output mode.
CliBackendOutput = Literal["json", "text", "jsonl"]


#: CliBackend JSONL dialect.
CliBackendJsonlDialect = Literal["claude-stream-json", "gemini-stream-json"]


#: CliBackend live session mode.
CliBackendLiveSession = Literal["claude-stdio"]


#: CliBackend prompt input mode.
CliBackendInputMode = Literal["arg", "stdin"]


#: CliBackend session mode.
CliBackendSessionMode = Literal["always", "existing", "none"]


#: CliBackend system prompt behavior.
CliBackendSystemPromptMode = Literal["append", "replace"]


#: CliBackend system prompt when-to-send mode.
CliBackendSystemPromptWhen = Literal["first", "always", "never"]


#: CliBackend image input mode.
CliBackendImageMode = Literal["repeat", "list"]


#: CliBackend image path scope.
CliBackendImagePathScope = Literal["temp", "workspace"]


class CliBackendWatchdogConfig(TypedDict, total=False):
    """No-output watchdog tuning (fresh or resume)."""
    noOutputTimeoutMs: int
    noOutputTimeoutRatio: float
    minMs: int
    maxMs: int


class CliBackendReliabilityConfig(TypedDict, total=False):
    """Runtime reliability tuning for this backend's process lifecycle."""
    outputLimits: dict
    watchdog: dict


class CliBackendConfig(TypedDict, total=False):
    """CLI backend config (e.g. claude, gemini)."""
    command: str
    args: list
    output: str  # CliBackendOutput
    resumeOutput: str  # CliBackendOutput
    jsonlDialect: str  # CliBackendJsonlDialect
    liveSession: str  # CliBackendLiveSession
    input: str  # CliBackendInputMode
    maxPromptArgChars: int
    env: dict
    clearEnv: list
    modelArg: str
    modelAliases: dict
    sessionArg: str
    sessionArgs: list
    resumeArgs: list
    forkArg: str
    sessionMode: str  # CliBackendSessionMode
    sessionIdFields: list
    systemPromptArg: str
    systemPromptFileArg: str
    systemPromptFileConfigArg: str
    systemPromptFileConfigKey: str
    systemPromptMode: str  # CliBackendSystemPromptMode
    systemPromptWhen: str  # CliBackendSystemPromptWhen
    imageArg: str
    imageMode: str  # CliBackendImageMode
    imagePathScope: str  # CliBackendImagePathScope
    serialize: bool
    reseedFromRawTranscriptWhenUncompacted: bool
    reliability: CliBackendReliabilityConfig


#: Agent heartbeat mode.
AgentHeartbeatMode = Literal["off", "available", "always"]


class AgentHeartbeatConfig(TypedDict, total=False):
    """Agent heartbeat config."""
    mode: str  # AgentHeartbeatMode
    intervalMs: int


#: Sub-agent delegation mode.
SubagentConfig = TypedDict  # {delegationMode?, allowAgents?, model?, thinking?, requireAgentId?}


class AgentIdentityAvatarConfig(TypedDict, total=False):
    """Agent identity avatar config."""
    url: str
    path: str


class AgentIdentityConfig(TypedDict, total=False):
    """Agent identity config (subset of types.base.IdentityConfig)."""
    name: str
    avatar: object  # str | AgentIdentityAvatarConfig


class AgentCompactionConfig(TypedDict, total=False):
    """Compaction policy for agent transcripts."""
    mode: str
    keepLastAssistants: int
    reserveTokens: int
    softTrimRatio: float
    hardClearRatio: float
    minPrunableToolChars: int
    memoryFlush: dict
    postCompactionContext: dict


class AgentFastModeConfig(TypedDict, total=False):
    """Agent fast mode config."""
    enabled: bool
    model: object
    autoOnSeconds: int


class AgentDefaultsConfig(TypedDict, total=False):
    """Top-level agents.defaults config."""
    params: dict
    model: object  # str | AgentModelListConfig
    utilityModel: str
    agentRuntime: dict
    imageModel: object
    imageGenerationModel: object
    videoGenerationModel: object
    musicGenerationModel: object
    voiceModel: object
    mediaGenerationAutoProviderFallback: bool
    pdfModel: object
    pdfMaxBytesMb: int
    pdfMaxPages: int
    models: dict
    modelPolicy: AgentModelPolicyConfig
    workspace: str
    skills: list
    silentReply: dict
    repoRoot: str
    promptOverlays: PromptOverlaysConfig
    skipBootstrap: bool
    skipOptionalBootstrapFiles: list  # OptionalBootstrapFileName[]
    bootstrapMaxChars: int
    bootstrapTotalMaxChars: int
    contextInjection: str  # AgentContextInjection
    experimental: dict
    compaction: AgentCompactionConfig
    thinkingDefault: str  # AgentThinkingLevel
    verboseDefault: str
    toolProgressDetail: str
    reasoningDefault: str
    fastModeDefault: AgentFastModeConfig
    heartbeat: AgentHeartbeatConfig
    memorySearch: dict
    humanDelay: dict
    tts: dict
    skillsLimits: dict
    contextLimits: AgentContextLimitsConfig
    contextTokens: int
    identity: AgentIdentityConfig
    groupChat: dict
    subagents: SubagentConfig
    runRetries: AgentRunRetriesConfig
    embeddedAgent: dict
    sandbox: dict
    prune: AgentContextPruningConfig
    startupContext: AgentStartupContextConfig
    tools: dict
    cliBackends: dict  # Record<string, CliBackendConfig>


__all__ = [
    "AgentContextInjection",
    "OptionalBootstrapFileName",
    "EmbeddedAgentExecutionContract",
    "SubagentDelegationMode",
    "AgentImageQualityPreference",
    "AgentThinkingLevel",
    "Gpt5Personality",
    "Gpt5PromptOverlayConfig",
    "PromptOverlaysConfig",
    "AgentModelEntryConfig",
    "AgentModelPolicyConfig",
    "AgentModelListConfig",
    "AgentContextPruningMode",
    "AgentContextPruningToolsConfig",
    "AgentContextPruningSoftTrimConfig",
    "AgentContextPruningHardClearConfig",
    "AgentContextPruningConfig",
    "AgentStartupContextConfig",
    "AgentContextLimitsConfig",
    "AgentRunRetriesConfig",
    "CliBackendOutput",
    "CliBackendJsonlDialect",
    "CliBackendLiveSession",
    "CliBackendInputMode",
    "CliBackendSessionMode",
    "CliBackendSystemPromptMode",
    "CliBackendSystemPromptWhen",
    "CliBackendImageMode",
    "CliBackendImagePathScope",
    "CliBackendWatchdogConfig",
    "CliBackendReliabilityConfig",
    "CliBackendConfig",
    "AgentHeartbeatMode",
    "AgentHeartbeatConfig",
    "SubagentConfig",
    "AgentIdentityAvatarConfig",
    "AgentIdentityConfig",
    "AgentCompactionConfig",
    "AgentFastModeConfig",
    "AgentDefaultsConfig",
]
