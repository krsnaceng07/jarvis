"""jarvis.config.types_slack — Slack channel configuration types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.slack.ts``.

Focused minimal port: TypedDict shapes + Literal unions for the
``SlackConfig`` family. Cross-references to other channel types
(``types.base``, ``types.messages``, ``types.secrets``, etc.) are
preserved as :data:`dict` aliases since the Python port already
exposes the canonical shape via :mod:`jarvis.config.types_base`
and :mod:`jarvis.config.types_messages`.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Slack presence polling/wake mode.
SlackPresenceEventsMode = Literal["off", "auto", "on"]


class SlackPresenceEventsConfig(TypedDict, total=False):
    """Slack presence polling and agent wake mode."""
    mode: str  # SlackPresenceEventsMode


#: Slack reaction notification mode.
SlackReactionNotificationMode = Literal["off", "own", "all", "allowlist"]


#: Slack streaming mode.
SlackStreamingMode = Literal["off", "partial", "block", "progress"]


#: Reply threading control.
ReplyToMode = Literal["off", "first", "all", "batched"]


#: Reply style for MS Teams (kept for cross-config parity).
MSTeamsReplyStyle = Literal["thread", "top-level"]


class SlackStreamingProgressConfig(TypedDict, total=False):
    """Progress-mode streaming config for Slack."""
    label: object  # str | false
    labels: list
    maxLines: int
    maxLineChars: int
    render: str
    toolProgress: bool
    commandText: str
    commentary: bool
    narration: bool
    # Slack-specific
    nativeTaskCards: bool


class SlackChannelStreamingConfig(TypedDict, total=False):
    """Slack streaming + chunking settings."""
    mode: str  # StreamingMode
    chunkMode: str
    nativeTransport: bool
    preview: dict
    progress: SlackStreamingProgressConfig
    block: dict


#: Slack exec-approval target.
SlackExecApprovalTarget = Literal["dm", "channel", "both"]


#: Native exec approval enable mode (bool or "auto").
NativeExecApprovalEnableMode = object  # bool | "auto"


class SlackExecApprovalConfig(TypedDict, total=False):
    """Slack-native exec approval delivery + approver authorization."""
    enabled: object  # NativeExecApprovalEnableMode
    approvers: list
    agentFilter: list
    sessionFilter: list
    target: str  # SlackExecApprovalTarget


#: Slack capability flags (array or object form).
SlackCapabilitiesConfig = object  # string[] | {interactiveReplies?: bool}


class SlackActionConfig(TypedDict, total=False):
    """Per-action tool gating."""
    reactions: bool
    messages: bool
    pins: bool
    search: bool
    permissions: bool
    memberInfo: bool
    channelInfo: bool
    emojiList: bool


class SlackSlashCommandConfig(TypedDict, total=False):
    """Slack slash command handling."""
    enabled: bool
    name: str
    sessionPrefix: str
    ephemeral: bool


class SlackThreadConfig(TypedDict, total=False):
    """Slack thread session behavior."""
    historyScope: str  # "thread" | "channel"
    inheritParent: bool
    initialHistoryLimit: int


class SlackSocketModeConfig(TypedDict, total=False):
    """Slack SDK Socket Mode transport options."""
    clientPingTimeout: int
    serverPingTimeout: int
    pingPongLoggingEnabled: bool


class SlackRelayConfig(TypedDict, total=False):
    """Relay-delivered Slack event source."""
    url: str
    authToken: object  # SecretInput
    gatewayId: str


class SlackChannelConfig(TypedDict, total=False):
    """Per-channel Slack configuration."""
    enabled: bool
    requireMention: bool
    ignoreOtherMentions: bool
    replyToMode: str  # ReplyToMode
    tools: dict
    toolsBySender: dict
    allowBots: object  # bool | "mentions"
    botLoopProtection: dict
    users: list
    skills: list
    systemPrompt: str
    presenceEvents: SlackPresenceEventsConfig


class SlackDmConfig(TypedDict, total=False):
    """Slack DM configuration."""
    enabled: bool
    policy: str  # DmPolicy
    allowFrom: list
    groupEnabled: bool
    groupChannels: list
    replyToMode: str  # ReplyToMode (legacy)


class SlackAccountConfig(TypedDict, total=False):
    """Per-account Slack configuration."""
    name: str
    identity: str  # "bot" | "user"
    mode: str  # "socket" | "http" | "relay"
    enterpriseOrgInstall: bool
    socketMode: SlackSocketModeConfig
    relay: SlackRelayConfig
    signingSecret: object  # SecretInput
    webhookPath: str
    capabilities: object  # SlackCapabilitiesConfig
    execApprovals: SlackExecApprovalConfig
    markdown: dict
    commands: dict  # ProviderCommandsConfig
    configWrites: bool
    enabled: bool
    botToken: object  # SecretInput
    appToken: object  # SecretInput
    userToken: object  # SecretInput
    userTokenReadOnly: bool
    allowBots: object
    botLoopProtection: dict
    dangerouslyAllowNameMatching: bool
    requireMention: bool
    implicitMentions: dict
    groupPolicy: str
    mentionPatterns: dict
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    unfurlLinks: bool
    unfurlMedia: bool
    streaming: SlackChannelStreamingConfig
    mediaMaxMb: int
    reactionNotifications: str
    reactionAllowlist: list
    replyToMode: str
    replyToModeByChatType: dict
    thread: SlackThreadConfig
    presenceEvents: SlackPresenceEventsConfig
    actions: SlackActionConfig
    slashCommand: SlackSlashCommandConfig
    dmPolicy: str  # canonical DM policy key
    allowFrom: list  # canonical DM allowlist
    defaultTo: str
    dm: SlackDmConfig
    channels: dict
    heartbeat: dict
    healthMonitor: dict
    responsePrefix: str
    ackReaction: str
    typingReaction: str


class SlackConfig(SlackAccountConfig, total=False):
    """Top-level Slack config — SlackAccountConfig + multi-account keys."""
    accounts: dict
    defaultAccount: str


__all__ = [
    "SlackPresenceEventsMode",
    "SlackPresenceEventsConfig",
    "SlackReactionNotificationMode",
    "SlackStreamingMode",
    "ReplyToMode",
    "MSTeamsReplyStyle",
    "SlackStreamingProgressConfig",
    "SlackChannelStreamingConfig",
    "SlackExecApprovalTarget",
    "NativeExecApprovalEnableMode",
    "SlackExecApprovalConfig",
    "SlackCapabilitiesConfig",
    "SlackActionConfig",
    "SlackSlashCommandConfig",
    "SlackThreadConfig",
    "SlackSocketModeConfig",
    "SlackRelayConfig",
    "SlackChannelConfig",
    "SlackDmConfig",
    "SlackAccountConfig",
    "SlackConfig",
]
