"""jarvis.config.types_discord — Discord channel configuration types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.discord.ts``.

Focused minimal port: TypedDict shapes + Literal unions for the
``DiscordConfig`` family. Cross-references to other channel types
(``types.base``, ``types.messages``, ``types.secrets``, etc.) are
preserved as :data:`dict` aliases.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Discord stream mode.
DiscordStreamMode = Literal["off", "partial", "block", "progress"]


#: Discord auto-archive thread duration.
DiscordAutoArchiveDuration = object  # "60" | "1440" | "4320" | "10080" | 60 | 1440 | 4320 | 10080


#: Discord auto-thread naming strategy.
DiscordAutoThreadName = Literal["message", "generated"]


#: Discord reaction notification mode.
DiscordReactionNotificationMode = Literal["off", "own", "all", "allowlist"]


#: Discord voice mode.
DiscordVoiceMode = Literal["stt-tts", "agent-proxy", "bidi"]


#: Discord voice realtime consult policy.
DiscordVoiceRealtimeConsultPolicy = Literal["auto", "always"]


#: Discord voice realtime tool policy.
DiscordVoiceRealtimeToolPolicy = Literal["safe-read-only", "owner", "none"]


#: Discord voice realtime bootstrap context files.
DiscordVoiceRealtimeBootstrapContextFile = Literal["IDENTITY.md", "USER.md", "SOUL.md"]


#: Discord exec-approval target.
DiscordExecApprovalTarget = Literal["dm", "channel", "both"]


#: Native exec approval enable mode (bool or "auto").
NativeExecApprovalEnableMode = object  # bool | "auto"


#: Discord activity type (0-5).
DiscordActivityType = Literal[0, 1, 2, 3, 4, 5]


#: Discord status.
DiscordStatus = Literal["online", "dnd", "idle", "invisible"]


#: Discord ack reaction scope.
DiscordAckReactionScope = Literal["group-mentions", "group-all", "direct", "all", "off", "none"]


class DiscordStreamProgressConfig(TypedDict, total=False):
    """Discord progress streaming config (subset)."""
    label: object  # str | false
    labels: list
    maxLines: int
    maxLineChars: int
    render: str
    toolProgress: bool
    commandText: str
    commentary: bool
    narration: bool


class DiscordChannelStreamingConfig(TypedDict, total=False):
    """Discord channel streaming config."""
    mode: str  # DiscordStreamMode
    chunkMode: str
    preview: dict
    progress: DiscordStreamProgressConfig
    block: dict


class DiscordPluralKitConfig(TypedDict, total=False):
    """PluralKit identity resolution config."""
    enabled: bool
    token: str


#: Discord mention aliases mapping.
DiscordMentionAliasesConfig = dict  # Record<string, string>


class DiscordDmConfig(TypedDict, total=False):
    """Discord DM config."""
    enabled: bool
    policy: str
    allowFrom: list
    groupEnabled: bool
    groupChannels: list


class DiscordGuildChannelConfig(TypedDict, total=False):
    """Per-channel Discord guild config."""
    requireMention: bool
    ignoreOtherMentions: bool
    tools: dict
    toolsBySender: dict
    skills: list
    enabled: bool
    users: list
    roles: list
    systemPrompt: str
    includeThreadStarter: bool
    autoThread: bool
    autoArchiveDuration: object  # DiscordAutoArchiveDuration
    autoThreadName: str  # DiscordAutoThreadName


class DiscordGuildEntry(TypedDict, total=False):
    """Per-guild Discord entry."""
    slug: str
    requireMention: bool
    ignoreOtherMentions: bool
    tools: dict
    toolsBySender: dict
    reactionNotifications: str
    users: list
    roles: list
    presenceEvents: dict
    channels: dict


class DiscordActionConfig(TypedDict, total=False):
    """Per-action tool gating for Discord."""
    reactions: bool
    stickers: bool
    polls: bool
    permissions: bool
    messages: bool
    threads: bool
    pins: bool
    search: bool
    memberInfo: bool
    roleInfo: bool
    roles: bool
    channelInfo: bool
    voiceStatus: bool
    events: bool
    moderation: bool
    emojiUploads: bool
    stickerUploads: bool
    channels: bool
    presence: bool


class DiscordIntentsConfig(TypedDict, total=False):
    """Discord privileged gateway intents config."""
    presence: bool
    guildMembers: bool
    voiceStates: bool


class DiscordVoiceAutoJoinConfig(TypedDict, total=False):
    """Voice auto-join target."""
    guildId: str
    channelId: str


class DiscordVoiceAllowedChannelConfig(TypedDict, total=False):
    """Voice allowed-channel entry."""
    guildId: str
    channelId: str


class DiscordVoiceRealtimeConfig(TypedDict, total=False):
    """Discord voice realtime provider config."""
    provider: str
    model: str
    speakerVoice: str
    speakerVoiceId: str
    voice: str  # deprecated
    instructions: str
    toolPolicy: str
    consultPolicy: str
    requireWakeName: object  # bool
    wakeNames: list
    bootstrapContextFiles: list
    bargeIn: bool
    minBargeInAudioEndMs: int
    debounceMs: int
    providers: dict


class DiscordVoiceAgentSessionConfig(TypedDict, total=False):
    """Discord voice agent session routing."""
    mode: str  # "voice" | "target"
    target: str


class DiscordVoiceConfig(TypedDict, total=False):
    """Discord voice channel config."""
    enabled: bool
    mode: str  # DiscordVoiceMode
    agentSession: DiscordVoiceAgentSessionConfig
    model: str
    realtime: DiscordVoiceRealtimeConfig
    autoJoin: list
    followUsersEnabled: bool
    followUsers: list
    allowedChannels: list
    daveEncryption: bool
    decryptionFailureTolerance: int
    connectTimeoutMs: int
    reconnectGraceMs: int
    captureSilenceGraceMs: int
    tts: dict


class DiscordExecApprovalConfig(TypedDict, total=False):
    """Discord exec-approval config."""
    enabled: object  # NativeExecApprovalEnableMode
    approvers: list
    agentFilter: list
    sessionFilter: list
    cleanupAfterResolve: bool
    target: str  # DiscordExecApprovalTarget


class DiscordAgentComponentsConfig(TypedDict, total=False):
    """Discord agent-controlled components config."""
    enabled: bool
    ttlMs: int


class DiscordUiComponentsConfig(TypedDict, total=False):
    """Discord UI components styling."""
    accentColor: str


class DiscordUiConfig(TypedDict, total=False):
    """Discord UI customization."""
    components: DiscordUiComponentsConfig


class DiscordThreadBindingsConfig(TypedDict, total=False):
    """Discord thread-bindings config."""
    enabled: bool
    idleHours: int
    maxAgeHours: int
    spawnSessions: bool
    defaultSpawnContext: str
    spawnSubagentSessions: bool  # deprecated
    spawnAcpSessions: bool  # deprecated


class DiscordSlashCommandConfig(TypedDict, total=False):
    """Discord slash command handling."""
    ephemeral: bool


class DiscordThreadConfig(TypedDict, total=False):
    """Discord thread session behavior."""
    inheritParent: bool


class DiscordAutoPresenceConfig(TypedDict, total=False):
    """Discord auto-presence config."""
    enabled: bool
    intervalMs: int
    minUpdateIntervalMs: int
    healthyText: str
    degradedText: str
    exhaustedText: str


class DiscordInboundWorkerConfig(TypedDict, total=False):
    """Legacy compatibility block — currently ignored."""
    runTimeoutMs: int


class DiscordEventQueueConfig(TypedDict, total=False):
    """Discord event-queue tuning."""
    listenerTimeout: int
    maxQueueSize: int
    maxConcurrency: int


class DiscordAccountConfig(TypedDict, total=False):
    """Per-account Discord configuration."""
    name: str
    capabilities: list
    markdown: dict
    commands: dict
    configWrites: bool
    enabled: bool
    token: object  # SecretInput
    applicationId: str
    activities: dict
    proxy: str
    gatewayInfoTimeoutMs: int
    gatewayReadyTimeoutMs: int
    gatewayRuntimeReadyTimeoutMs: int
    allowBots: object  # bool | "mentions"
    botLoopProtection: dict
    dangerouslyAllowNameMatching: bool
    mentionAliases: DiscordMentionAliasesConfig
    groupPolicy: str
    mentionPatterns: dict
    contextVisibility: str
    textChunkLimit: int
    suppressEmbeds: bool
    streaming: DiscordChannelStreamingConfig
    maxLinesPerMessage: int
    mediaMaxMb: int
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    retry: dict
    actions: DiscordActionConfig
    replyToMode: str
    thread: DiscordThreadConfig
    dmPolicy: str
    allowFrom: list
    defaultTo: str
    dm: DiscordDmConfig
    guilds: dict
    heartbeat: dict
    healthMonitor: dict
    execApprovals: DiscordExecApprovalConfig
    agentComponents: DiscordAgentComponentsConfig
    ui: DiscordUiConfig
    slashCommand: DiscordSlashCommandConfig
    threadBindings: DiscordThreadBindingsConfig
    subagentProgress: bool
    intents: DiscordIntentsConfig
    voice: DiscordVoiceConfig
    pluralkit: DiscordPluralKitConfig
    responsePrefix: str
    ackReaction: str
    ackReactionScope: str  # DiscordAckReactionScope
    activity: str
    status: str  # DiscordStatus
    autoPresence: DiscordAutoPresenceConfig
    activityType: int  # DiscordActivityType
    activityUrl: str
    inboundWorker: DiscordInboundWorkerConfig
    eventQueue: DiscordEventQueueConfig


class DiscordConfig(DiscordAccountConfig, total=False):
    """Top-level Discord config — DiscordAccountConfig + multi-account keys."""
    accounts: dict
    defaultAccount: str


__all__ = [
    "DiscordStreamMode",
    "DiscordAutoArchiveDuration",
    "DiscordAutoThreadName",
    "DiscordReactionNotificationMode",
    "DiscordVoiceMode",
    "DiscordVoiceRealtimeConsultPolicy",
    "DiscordVoiceRealtimeToolPolicy",
    "DiscordVoiceRealtimeBootstrapContextFile",
    "DiscordExecApprovalTarget",
    "NativeExecApprovalEnableMode",
    "DiscordActivityType",
    "DiscordStatus",
    "DiscordAckReactionScope",
    "DiscordStreamProgressConfig",
    "DiscordChannelStreamingConfig",
    "DiscordPluralKitConfig",
    "DiscordMentionAliasesConfig",
    "DiscordDmConfig",
    "DiscordGuildChannelConfig",
    "DiscordGuildEntry",
    "DiscordActionConfig",
    "DiscordIntentsConfig",
    "DiscordVoiceAutoJoinConfig",
    "DiscordVoiceAllowedChannelConfig",
    "DiscordVoiceRealtimeConfig",
    "DiscordVoiceAgentSessionConfig",
    "DiscordVoiceConfig",
    "DiscordExecApprovalConfig",
    "DiscordAgentComponentsConfig",
    "DiscordUiComponentsConfig",
    "DiscordUiConfig",
    "DiscordThreadBindingsConfig",
    "DiscordSlashCommandConfig",
    "DiscordThreadConfig",
    "DiscordAutoPresenceConfig",
    "DiscordInboundWorkerConfig",
    "DiscordEventQueueConfig",
    "DiscordAccountConfig",
    "DiscordConfig",
]
