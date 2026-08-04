"""jarvis.config.types_agents_shared — shared agent config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.agents-shared.ts``.
"""
from __future__ import annotations

from typing import TypedDict


#: Agent model selector: a string or primary+fallback chain.
AgentModelConfig = dict  # str | {primary?, fallbacks?}

#: Tool-specific model selector with optional capability timeout.
AgentToolModelConfig = dict  # str | {primary?, fallbacks?, timeoutMs?}


class AgentRuntimePolicyConfig(TypedDict, total=False):
    id: str


class AgentSandboxConfig(TypedDict, total=False):
    """Per-agent sandbox policy shared by embedded agents and sandbox backends."""

    mode: str
    backend: str
    workspaceAccess: str
    sessionToolsVisibility: str
    scope: str
    workspaceRoot: str
    docker: dict
    ssh: dict
    browser: dict
    prune: dict


__all__ = [
    "AgentModelConfig",
    "AgentToolModelConfig",
    "AgentRuntimePolicyConfig",
    "AgentSandboxConfig",
]
