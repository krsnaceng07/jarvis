"""jarvis.config.types_googlechat — Google Chat channel config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.googlechat.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Google Chat audience type.
GoogleChatAudienceType = Literal["app-url", "project-number"]
#: Google Chat typing indicator mode.
GoogleChatTypingIndicator = Literal["none", "message", "reaction"]


class GoogleChatDmConfig(TypedDict, total=False):
    enabled: bool
    policy: str
    allowFrom: list


class GoogleChatGroupConfig(TypedDict, total=False):
    enabled: bool
    requireMention: bool
    botLoopProtection: dict
    users: list
    systemPrompt: str


class GoogleChatActionConfig(TypedDict, total=False):
    reactions: bool


class GoogleChatAccountConfig(TypedDict, total=False):
    name: str
    capabilities: list
    configWrites: bool
    enabled: bool
    allowBots: bool
    botLoopProtection: dict
    dangerouslyAllowNameMatching: bool
    requireMention: bool
    groupPolicy: str
    groupAllowFrom: list
    defaultTo: str
    groups: dict
    serviceAccount: object
    serviceAccountRef: dict
    serviceAccountFile: str
    audienceType: str
    audience: str
    appPrincipal: str
    webhookPath: str
    webhookUrl: str
    botUser: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    streaming: dict
    mediaMaxMb: int
    replyToMode: str
    actions: GoogleChatActionConfig
    dm: GoogleChatDmConfig
    healthMonitor: dict
    typingIndicator: str
    responsePrefix: str


class GoogleChatConfig(TypedDict, total=False):
    accounts: dict
    defaultAccount: str
    # AccountConfig fields may also appear at top level.
    name: str
    capabilities: list
    configWrites: bool
    enabled: bool
    allowBots: bool
    botLoopProtection: dict
    dangerouslyAllowNameMatching: bool
    requireMention: bool
    groupPolicy: str
    groupAllowFrom: list
    defaultTo: str
    groups: dict
    serviceAccount: object
    serviceAccountRef: dict
    serviceAccountFile: str
    audienceType: str
    audience: str
    appPrincipal: str
    webhookPath: str
    webhookUrl: str
    botUser: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    streaming: dict
    mediaMaxMb: int
    replyToMode: str
    actions: GoogleChatActionConfig
    dm: GoogleChatDmConfig
    healthMonitor: dict
    typingIndicator: str
    responsePrefix: str


__all__ = [
    "GoogleChatAudienceType",
    "GoogleChatTypingIndicator",
    "GoogleChatDmConfig",
    "GoogleChatGroupConfig",
    "GoogleChatActionConfig",
    "GoogleChatAccountConfig",
    "GoogleChatConfig",
]
