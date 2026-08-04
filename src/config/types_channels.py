"""jarvis.config.types_channels — shared channel config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.channels.ts``.

Focused minimal port: exposes ``ChannelsConfig`` (the umbrella per-
channel config) and shared defaults + extension shapes. The per-
channel config types are referenced through duck-typed dicts since
the upstream uses a TypeScript open-world pattern.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Group admission policy for channel providers.
GroupPolicy = str  # "open" | "disabled" | "allowlist"
#: Context visibility mode.
ContextVisibilityMode = str  # "all" | "allowlist" | "allowlist_quote"


class ChannelDefaultsConfig(TypedDict, total=False):
    groupPolicy: str
    contextVisibility: str
    heartbeat: dict
    botLoopProtection: dict
    implicitMentions: dict


#: Per-channel/per-target model override map.
ChannelModelByChannelConfig = dict


class ExtensionNestedPolicyConfig(TypedDict, total=False):
    policy: str
    allowFrom: list


class ExtensionAccountConfig(ExtensionNestedPolicyConfig, total=False):
    defaultTo: object
    dmPolicy: str
    dm: ExtensionNestedPolicyConfig
    mediaMaxMb: int
    configWrites: bool
    implicitMentions: dict


class ThreadBindingsConfig(TypedDict, total=False):
    enabled: bool
    spawnSessions: bool
    defaultSpawnContext: str
    spawnAcpSessions: bool
    spawnSubagentSessions: bool


class ExtensionChannelConfig(TypedDict, total=False):
    enabled: bool
    allowFrom: list
    defaultTo: object
    defaultAccount: str
    dmPolicy: str
    groupPolicy: str
    mentionPatterns: object
    contextVisibility: str
    healthMonitor: dict
    dm: ExtensionNestedPolicyConfig
    network: dict
    groups: dict
    rooms: dict
    mediaMaxMb: int
    callbackBaseUrl: str
    interactions: dict
    execApprovals: dict
    threadBindings: ThreadBindingsConfig
    botLoopProtection: dict
    implicitMentions: dict
    spawnSubagentSessions: bool
    dangerouslyAllowPrivateNetwork: bool
    accounts: dict


#: JSON-compatible open-world channel section.
OpenWorldChannelConfig = dict


class ChannelsConfig(TypedDict, total=False):
    defaults: ChannelDefaultsConfig
    modelByChannel: ChannelModelByChannelConfig
    # The per-provider config sections (referenced as open-world dicts).
    discord: dict
    googlechat: dict
    imessage: dict
    irc: dict
    msteams: dict
    signal: dict
    slack: dict
    telegram: dict
    whatsapp: dict


__all__ = [
    "GroupPolicy",
    "ContextVisibilityMode",
    "ChannelDefaultsConfig",
    "ChannelModelByChannelConfig",
    "ExtensionNestedPolicyConfig",
    "ExtensionAccountConfig",
    "ThreadBindingsConfig",
    "ExtensionChannelConfig",
    "OpenWorldChannelConfig",
    "ChannelsConfig",
]
