"""jarvis.config.types_imessage — iMessage channel config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.imessage.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: iMessage service kind.
IMessageService = Literal["imessage", "sms", "auto"]
#: iMessage send transport.
IMessageSendTransport = Literal["auto", "bridge", "applescript"]
#: iMessage reaction notification mode.
IMessageReactionNotificationMode = Literal["off", "own", "all"]


class IMessageActionConfig(TypedDict, total=False):
    reactions: bool
    edit: bool
    unsend: bool
    reply: bool
    sendWithEffect: bool
    renameGroup: bool
    setGroupIcon: bool
    addParticipant: bool
    removeParticipant: bool
    leaveGroup: bool
    sendAttachment: bool
    polls: bool


class IMessageGroupConfig(TypedDict, total=False):
    requireMention: bool
    tools: dict
    toolsBySender: dict
    systemPrompt: str


class IMessageCatchupConfig(TypedDict, total=False):
    enabled: bool
    maxAgeMinutes: int
    perRunLimit: int
    firstRunLookbackMinutes: int
    maxFailureRetries: int


class IMessageAccountConfig(TypedDict, total=False):
    name: str
    capabilities: list
    markdown: dict
    configWrites: bool
    enabled: bool
    cliPath: str
    dbPath: str
    remoteHost: str
    actions: IMessageActionConfig
    service: str
    sendTransport: str
    region: str
    dmPolicy: str
    allowFrom: list
    defaultTo: str
    groupAllowFrom: list
    groupPolicy: str
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    includeAttachments: bool
    attachmentRoots: list
    remoteAttachmentRoots: list
    mediaMaxMb: int
    probeTimeoutMs: int
    textChunkLimit: int
    streaming: dict
    sendReadReceipts: bool
    reactionNotifications: str
    coalesceSameSenderDms: bool
    groups: dict
    catchup: IMessageCatchupConfig
    heartbeat: dict
    healthMonitor: dict
    responsePrefix: str


class IMessageConfig(TypedDict, total=False):
    accounts: dict
    defaultAccount: str
    # AccountConfig fields may also appear at top level.
    name: str
    capabilities: list
    markdown: dict
    configWrites: bool
    enabled: bool
    cliPath: str
    dbPath: str
    remoteHost: str
    actions: IMessageActionConfig
    service: str
    sendTransport: str
    region: str
    dmPolicy: str
    allowFrom: list
    defaultTo: str
    groupAllowFrom: list
    groupPolicy: str
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    includeAttachments: bool
    attachmentRoots: list
    remoteAttachmentRoots: list
    mediaMaxMb: int
    probeTimeoutMs: int
    textChunkLimit: int
    streaming: dict
    sendReadReceipts: bool
    reactionNotifications: str
    coalesceSameSenderDms: bool
    groups: dict
    catchup: IMessageCatchupConfig
    heartbeat: dict
    healthMonitor: dict
    responsePrefix: str


__all__ = [
    "IMessageService",
    "IMessageSendTransport",
    "IMessageReactionNotificationMode",
    "IMessageActionConfig",
    "IMessageGroupConfig",
    "IMessageCatchupConfig",
    "IMessageAccountConfig",
    "IMessageConfig",
]
