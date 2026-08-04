"""jarvis.config.types_node_host — node-host-local capability config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.node-host.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class NodeHostBrowserProxyConfig(TypedDict, total=False):
    enabled: bool
    allowProfiles: list


class NodeHostAgentRunsClaudeConfig(TypedDict, total=False):
    enabled: bool


class NodeHostAgentRunsConfig(TypedDict, total=False):
    claude: NodeHostAgentRunsClaudeConfig


class NodeHostMcpConfig(TypedDict, total=False):
    servers: dict


class NodeHostSkillsConfig(TypedDict, total=False):
    enabled: bool


class NodeHostConfig(TypedDict, total=False):
    agentRuns: NodeHostAgentRunsConfig
    browserProxy: NodeHostBrowserProxyConfig
    mcp: NodeHostMcpConfig
    skills: NodeHostSkillsConfig


__all__ = [
    "NodeHostBrowserProxyConfig",
    "NodeHostAgentRunsClaudeConfig",
    "NodeHostAgentRunsConfig",
    "NodeHostMcpConfig",
    "NodeHostSkillsConfig",
    "NodeHostConfig",
]
