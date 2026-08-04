"""jarvis.config.types_hooks — hook configuration types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.hooks.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


#: Hook action kind.
HookAction = Literal["wake", "agent"]
#: Hook wake timing.
HookWakeMode = Literal["now", "next-heartbeat"]
#: Gmail tailscale exposure mode.
HooksGmailTailscaleMode = Literal["off", "serve", "funnel"]
#: Hook thinking level override.
HookThinkingLevel = Literal["off", "minimal", "low", "medium", "high"]


class HookMappingMatch(TypedDict, total=False):
    path: str
    source: str


class HookMappingTransform(TypedDict, total=False):
    module: str
    export: str


class HookMappingConfig(TypedDict, total=False):
    id: str
    match: HookMappingMatch
    action: str
    wakeMode: str
    name: str
    agentId: str
    sessionKey: str
    messageTemplate: str
    textTemplate: str
    deliver: bool
    allowUnsafeExternalContent: bool
    channel: str
    to: str
    model: str
    thinking: str
    timeoutSeconds: int
    transform: HookMappingTransform


class HooksGmailServeConfig(TypedDict, total=False):
    bind: str
    port: int
    path: str


class HooksGmailTailscaleConfig(TypedDict, total=False):
    mode: str
    path: str
    target: str


class HooksGmailConfig(TypedDict, total=False):
    account: str
    label: str
    topic: str
    subscription: str
    pushToken: str
    hookUrl: str
    includeBody: bool
    maxBytes: int
    renewEveryMinutes: int
    allowUnsafeExternalContent: bool
    serve: HooksGmailServeConfig
    tailscale: HooksGmailTailscaleConfig
    model: str
    thinking: str


class HookConfig(TypedDict, total=False):
    enabled: bool
    env: dict


#: Hook install record — broad shape covering all install sources.
HookInstallRecord = dict


class InternalHooksLoadConfig(TypedDict, total=False):
    extraDirs: list


class InternalHooksConfig(TypedDict, total=False):
    enabled: bool
    entries: dict
    load: InternalHooksLoadConfig
    installs: dict


class HooksConfig(TypedDict, total=False):
    enabled: bool
    path: str
    token: str
    defaultSessionKey: str
    allowRequestSessionKey: bool
    allowedSessionKeyPrefixes: list
    allowedAgentIds: list
    maxBodyBytes: int
    presets: list
    transformsDir: str
    mappings: list
    gmail: HooksGmailConfig
    internal: InternalHooksConfig


__all__ = [
    "HookAction",
    "HookWakeMode",
    "HooksGmailTailscaleMode",
    "HookThinkingLevel",
    "HookMappingMatch",
    "HookMappingTransform",
    "HookMappingConfig",
    "HooksGmailServeConfig",
    "HooksGmailTailscaleConfig",
    "HooksGmailConfig",
    "HookConfig",
    "HookInstallRecord",
    "InternalHooksLoadConfig",
    "InternalHooksConfig",
    "HooksConfig",
]
