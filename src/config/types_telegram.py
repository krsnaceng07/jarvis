"""jarvis.config.types_telegram — Telegram channel configuration types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.telegram.ts``.

Focused minimal port: TypedDict shapes + Literal unions for the
``TelegramConfig`` family. Cross-references to other channel types are
preserved as :data:`dict` aliases.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Reply threading control.
ReplyToMode = Literal["off", "first", "all", "batched"]


#: Inline buttons scope.
TelegramInlineButtonsScope = Literal["off", "dm", "group", "all", "allowlist"]


#: Telegram streaming mode.
TelegramStreamingMode = Literal["off", "partial", "block", "progress"]


#: Telegram exec-approval target.
TelegramExecApprovalTarget = Literal["dm", "channel", "both"]


#: Native exec approval enable mode (bool or "auto").
NativeExecApprovalEnableMode = object  # bool | "auto"


#: Reaction notification mode for Telegram.
TelegramReactionNotificationMode = Literal["off", "own", "all"]


#: Reaction level policy.
TelegramReactionLevel = Literal["off", "ack", "minimal", "extensive"]


#: Error policy for outbound error reporting.
TelegramErrorPolicy = Literal["always", "once", "silent"]


#: Legacy DM thread replies (kept for SDK compat).
TelegramDmThreadReplies = Literal["off", "inbound", "always"]


class TelegramActionConfig(TypedDict, total=False):
    """Per-action tool gating for Telegram."""
    reactions: bool
    sendMessage: bool
    poll: bool
    deleteMessage: bool
    editMessage: bool
    sticker: bool
    createForumTopic: bool
    editForumTopic: bool


class TelegramThreadBindingsConfig(TypedDict, total=False):
    """Telegram thread/conversation binding overrides."""
    enabled: bool
    idleHours: int
    # Legacy keys kept for compat.
    spawnSubagentSessions: bool
    spawnAcpSessions: bool
    spawnSessions: bool


class TelegramNetworkConfig(TypedDict, total=False):
    """Network transport overrides for Telegram."""
    autoSelectFamily: bool
    dnsResultOrder: str  # "ipv4first" | "verbatim"
    dangerouslyAllowPrivateNetwork: bool


class TelegramPreviewStreamingConfig(TypedDict, total=False):
    """Telegram preview streaming config."""
    mode: str
    chunkMode: str
    preview: dict
    progress: dict
    block: dict


class TelegramExecApprovalConfig(TypedDict, total=False):
    """Telegram-native exec approval delivery + approver authorization."""
    enabled: object  # NativeExecApprovalEnableMode
    approvers: list
    agentFilter: list
    sessionFilter: list
    target: str  # TelegramExecApprovalTarget


#: Telegram capability flags.
TelegramCapabilitiesConfig = object  # string[] | {inlineButtons?: TelegramInlineButtonsScope}


class TelegramCustomCommand(TypedDict, total=False):
    """Custom command definition for Telegram bot menu."""
    command: str
    description: str


#: Auto topic label config.
AutoTopicLabelConfig = object  # bool | {enabled?, prompt?}


class TelegramTopicConfig(TypedDict, total=False):
    """Per-topic Telegram config."""
    requireMention: bool
    ingest: bool
    groupPolicy: str
    skills: list
    enabled: bool
    allowFrom: list
    systemPrompt: str
    disableAudioPreflight: bool
    agentId: str
    errorPolicy: str
    errorCooldownMs: int


class TelegramGroupConfig(TypedDict, total=False):
    """Per-group Telegram config."""
    requireMention: bool
    ingest: bool
    groupPolicy: str
    tools: dict
    toolsBySender: dict
    skills: list
    topics: dict
    enabled: bool
    allowFrom: list
    systemPrompt: str
    disableAudioPreflight: bool
    errorPolicy: str
    errorCooldownMs: int


class TelegramDirectConfig(TypedDict, total=False):
    """Per-DM Telegram config (key is chat ID)."""
    dmPolicy: str
    threadReplies: str  # legacy
    tools: dict
    toolsBySender: dict
    skills: list
    topics: dict
    enabled: bool
    requireTopic: bool
    allowFrom: list
    systemPrompt: str
    errorPolicy: str
    errorCooldownMs: int
    autoTopicLabel: object  # AutoTopicLabelConfig


class TelegramDmConfig(TypedDict, total=False):
    """Legacy DM config (kept for compat)."""
    threadReplies: str


class TelegramAccountConfig(TypedDict, total=False):
    """Per-account Telegram configuration."""
    name: str
    capabilities: object  # TelegramCapabilitiesConfig
    execApprovals: TelegramExecApprovalConfig
    markdown: dict
    commands: dict  # ProviderCommandsConfig
    customCommands: list  # TelegramCustomCommand[]
    configWrites: bool
    dmPolicy: str
    enabled: bool
    botToken: str
    tokenFile: str
    replyToMode: str  # ReplyToMode
    dm: TelegramDmConfig
    groups: dict  # Record<chatId, TelegramGroupConfig>
    direct: dict  # Record<chatId, TelegramDirectConfig>
    allowFrom: list
    defaultTo: object  # str | number
    groupAllowFrom: list
    groupPolicy: str
    mentionPatterns: dict
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    richMessages: bool
    streaming: TelegramPreviewStreamingConfig
    mediaMaxMb: int
    timeoutSeconds: int
    mediaGroupFlushMs: int
    pollingStallThresholdMs: int
    retry: dict  # OutboundRetryConfig
    network: TelegramNetworkConfig
    proxy: str
    webhookUrl: str
    webhookSecret: str
    webhookPath: str
    webhookHost: str
    webhookPort: int
    webhookCertPath: str
    actions: TelegramActionConfig
    threadBindings: TelegramThreadBindingsConfig
    reactionNotifications: str
    reactionLevel: str
    heartbeat: dict
    healthMonitor: dict
    linkPreview: bool
    silentErrorReplies: bool
    errorPolicy: str
    errorCooldownMs: int
    responsePrefix: str
    ackReaction: str
    apiRoot: str
    trustedLocalFileRoots: list
    autoTopicLabel: object  # AutoTopicLabelConfig


class TelegramConfig(TelegramAccountConfig, total=False):
    """Top-level Telegram config — TelegramAccountConfig + multi-account keys."""
    accounts: dict
    defaultAccount: str


__all__ = [
    "ReplyToMode",
    "TelegramInlineButtonsScope",
    "TelegramStreamingMode",
    "TelegramExecApprovalTarget",
    "NativeExecApprovalEnableMode",
    "TelegramReactionNotificationMode",
    "TelegramReactionLevel",
    "TelegramErrorPolicy",
    "TelegramDmThreadReplies",
    "TelegramActionConfig",
    "TelegramThreadBindingsConfig",
    "TelegramNetworkConfig",
    "TelegramPreviewStreamingConfig",
    "TelegramExecApprovalConfig",
    "TelegramCapabilitiesConfig",
    "TelegramCustomCommand",
    "AutoTopicLabelConfig",
    "TelegramTopicConfig",
    "TelegramGroupConfig",
    "TelegramDirectConfig",
    "TelegramDmConfig",
    "TelegramAccountConfig",
    "TelegramConfig",
]
