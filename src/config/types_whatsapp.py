"""jarvis.config.types_whatsapp — WhatsApp channel config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.whatsapp.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: WhatsApp reaction level.
WhatsAppReactionLevel = str  # "off" | "ack" | "minimal" | "extensive"
#: WhatsApp group ack-reaction mode.
WhatsAppAckGroupMode = Literal["always", "mentions", "never"]


class WhatsAppActionConfig(TypedDict, total=False):
    reactions: bool
    sendMessage: bool
    polls: bool
    calls: bool


class WhatsAppGroupConfig(TypedDict, total=False):
    requireMention: bool
    tools: dict
    toolsBySender: dict
    systemPrompt: str


class WhatsAppDirectConfig(TypedDict, total=False):
    systemPrompt: str


class WhatsAppAckReactionConfig(TypedDict, total=False):
    emoji: str
    direct: bool
    group: str


class WhatsAppPluginHooksConfig(TypedDict, total=False):
    messageReceived: bool


class WhatsAppAccountConfig(TypedDict, total=False):
    name: str
    capabilities: list
    markdown: dict
    configWrites: bool
    sendReadReceipts: bool
    messagePrefix: str
    responsePrefix: str
    enabled: bool
    authDir: str
    pluginHooks: WhatsAppPluginHooksConfig
    # Shared config (inline)
    dmPolicy: str
    selfChatMode: bool
    allowFrom: list
    defaultTo: str
    groupAllowFrom: list
    groupPolicy: str
    mentionPatterns: object
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    streaming: dict
    mediaMaxMb: int
    groups: dict
    direct: dict
    ackReaction: WhatsAppAckReactionConfig
    reactionLevel: str
    debounceMs: int
    replyToMode: str
    heartbeat: dict
    healthMonitor: dict


class WhatsAppConfig(TypedDict, total=False):
    capabilities: list
    markdown: dict
    configWrites: bool
    sendReadReceipts: bool
    messagePrefix: str
    responsePrefix: str
    accounts: dict
    defaultAccount: str
    actions: WhatsAppActionConfig
    pluginHooks: WhatsAppPluginHooksConfig
    # Shared
    enabled: bool
    dmPolicy: str
    selfChatMode: bool
    allowFrom: list
    defaultTo: str
    groupAllowFrom: list
    groupPolicy: str
    mentionPatterns: object
    contextVisibility: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    streaming: dict
    mediaMaxMb: int
    groups: dict
    direct: dict
    ackReaction: WhatsAppAckReactionConfig
    reactionLevel: str
    debounceMs: int
    replyToMode: str
    heartbeat: dict
    healthMonitor: dict


__all__ = [
    "WhatsAppReactionLevel",
    "WhatsAppAckGroupMode",
    "WhatsAppActionConfig",
    "WhatsAppGroupConfig",
    "WhatsAppDirectConfig",
    "WhatsAppAckReactionConfig",
    "WhatsAppPluginHooksConfig",
    "WhatsAppAccountConfig",
    "WhatsAppConfig",
]
