"""jarvis.config.types_signal — Signal channel config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.signal.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


SignalReactionNotificationMode = Literal["off", "own", "all", "allowlist"]
SignalReactionLevel = Literal["off", "ack", "minimal", "extensive"]
SignalApiMode = Literal["auto", "native", "container"]


class SignalGroupConfig(TypedDict, total=False):
    requireMention: bool
    ingest: bool
    tools: dict
    toolsBySender: dict


class SignalActionsConfig(TypedDict, total=False):
    reactions: bool


class SignalAccountConfig(TypedDict, total=False):
    """CommonChannelMessagingConfig + Signal-specific fields."""

    name: str
    capabilities: list
    markdown: dict
    configWrites: bool
    enabled: bool
    dmPolicy: str
    allowFrom: list
    defaultTo: str
    groupAllowFrom: list
    groupPolicy: str
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    streaming: dict
    heartbeat: dict
    healthMonitor: dict
    responsePrefix: str
    mediaMaxMb: int
    # Signal-specific
    account: str
    accountUuid: str
    configPath: str
    httpUrl: str
    httpHost: str
    httpPort: int
    cliPath: str
    autoStart: bool
    startupTimeoutMs: int
    receiveMode: str
    ignoreAttachments: bool
    ignoreStories: bool
    sendReadReceipts: bool
    aliases: dict
    groups: dict
    replyToMode: str
    replyToModeByChatType: dict
    reactionNotifications: str
    reactionAllowlist: list
    actions: SignalActionsConfig
    reactionLevel: str


class SignalConfig(TypedDict, total=False):
    apiMode: str
    accounts: dict
    defaultAccount: str
    # SignalAccountConfig fields may also appear at the top level.
    account: str
    accountUuid: str
    configPath: str
    httpUrl: str
    httpHost: str
    httpPort: int
    cliPath: str
    autoStart: bool
    startupTimeoutMs: int
    receiveMode: str
    ignoreAttachments: bool
    ignoreStories: bool
    sendReadReceipts: bool
    aliases: dict
    groups: dict
    textChunkLimit: int
    replyToMode: str
    replyToModeByChatType: dict
    reactionNotifications: str
    reactionAllowlist: list
    actions: SignalActionsConfig
    reactionLevel: str


__all__ = [
    "SignalReactionNotificationMode",
    "SignalReactionLevel",
    "SignalApiMode",
    "SignalGroupConfig",
    "SignalActionsConfig",
    "SignalAccountConfig",
    "SignalConfig",
]
