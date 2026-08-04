"""jarvis.config.types_irc — IRC channel config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.irc.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class IrcNickServConfig(TypedDict, total=False):
    enabled: bool
    service: str
    password: str
    passwordFile: str
    register: bool
    registerEmail: str


class IrcGroupConfig(TypedDict, total=False):
    requireMention: bool
    tools: dict
    toolsBySender: dict
    allowFrom: list
    skills: list
    enabled: bool
    systemPrompt: str


class IrcAccountConfig(TypedDict, total=False):
    """CommonChannelMessagingConfig + IRC-specific fields."""

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
    # IRC-specific
    host: str
    port: int
    tls: bool
    nick: str
    username: str
    realname: str
    password: str
    passwordFile: str
    nickserv: IrcNickServConfig
    channels: list
    groups: dict
    mentionPatterns: list


class IrcConfig(TypedDict, total=False):
    accounts: dict
    defaultAccount: str
    # IrcAccountConfig fields may also appear at the top level.
    host: str
    port: int
    tls: bool
    nick: str
    username: str
    realname: str
    password: str
    passwordFile: str
    nickserv: IrcNickServConfig
    channels: list
    textChunkLimit: int
    groups: dict
    mentionPatterns: list


__all__ = [
    "IrcNickServConfig",
    "IrcGroupConfig",
    "IrcAccountConfig",
    "IrcConfig",
]
