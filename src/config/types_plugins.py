"""jarvis.config.types_plugins — plugin entry/install config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.plugins.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict


BundledDiscoveryMode = Literal["compat", "allowlist"]


class PluginEntryHooksConfig(TypedDict, total=False):
    allowPromptInjection: bool
    allowConversationAccess: bool
    timeoutMs: int
    timeouts: dict


class PluginEntrySubagentConfig(TypedDict, total=False):
    allowModelOverride: bool
    allowedModels: list


class PluginEntryLlmConfig(TypedDict, total=False):
    allowModelOverride: bool
    allowedModels: list
    allowAgentIdOverride: bool


class PluginEntryConfig(TypedDict, total=False):
    enabled: bool
    hooks: PluginEntryHooksConfig
    subagent: PluginEntrySubagentConfig
    llm: PluginEntryLlmConfig
    config: dict


class PluginSlotsConfig(TypedDict, total=False):
    memory: str
    contextEngine: str


class PluginsLoadConfig(TypedDict, total=False):
    paths: list


#: Plugin install record — broad shape covering all install sources.
PluginInstallRecord = dict


class PluginsConfig(TypedDict, total=False):
    enabled: bool
    allow: list
    deny: list
    load: PluginsLoadConfig
    slots: PluginSlotsConfig
    entries: dict
    bundledDiscovery: str
    installs: dict


__all__ = [
    "BundledDiscoveryMode",
    "PluginEntryHooksConfig",
    "PluginEntrySubagentConfig",
    "PluginEntryLlmConfig",
    "PluginEntryConfig",
    "PluginSlotsConfig",
    "PluginsLoadConfig",
    "PluginInstallRecord",
    "PluginsConfig",
]
