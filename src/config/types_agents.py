"""jarvis.config.types_agents — agent routing/model/runtime config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.agents.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Agent runtime type.
AgentRuntimeType = Literal["embedded", "acp"]
#: ACP session mode.
AcpSessionMode = Literal["persistent", "oneshot"]
#: Per-agent verbose level.
AgentVerboseLevel = Literal["off", "on", "full"]
#: Per-agent reasoning visibility.
AgentReasoningDefault = Literal["on", "off", "stream"]
#: Per-agent subagent delegation mode.
SubagentDelegationMode = Literal["suggest", "prefer"]


class AgentRuntimeAcpConfig(TypedDict, total=False):
    agent: str
    backend: str
    mode: str
    cwd: str


class AgentRuntimeConfig(TypedDict, total=False):
    type: str
    acp: AgentRuntimeAcpConfig


class AgentBindingMatch(TypedDict, total=False):
    channel: str
    accountId: str
    peer: dict
    guildId: str
    teamId: str
    roles: list


class AgentRouteBinding(TypedDict, total=False):
    type: str
    agentId: str
    comment: str
    match: AgentBindingMatch
    session: dict


class AgentAcpBinding(TypedDict, total=False):
    type: str
    agentId: str
    comment: str
    match: AgentBindingMatch
    acp: dict


#: Agent binding union.
AgentBinding = dict


class AgentConfig(TypedDict, total=False):
    id: str
    default: bool
    name: str
    description: str
    workspace: str
    agentDir: str
    model: object
    utilityModel: str
    agentRuntime: object
    models: dict
    modelPolicy: dict
    compaction: dict
    thinkingDefault: str
    verboseDefault: str
    toolProgressDetail: str
    reasoningDefault: str
    fastModeDefault: object
    contextInjection: str
    bootstrapMaxChars: int
    bootstrapTotalMaxChars: int
    experimental: dict
    skills: list
    memorySearch: dict
    humanDelay: dict
    tts: dict
    skillsLimits: dict
    contextLimits: dict
    contextTokens: int
    heartbeat: dict
    identity: dict
    groupChat: dict
    subagents: dict
    runRetries: dict
    embeddedAgent: dict
    sandbox: dict
    params: dict
    tools: dict
    runtime: AgentRuntimeConfig


class AgentsConfig(TypedDict, total=False):
    defaults: dict
    list: list


__all__ = [
    "AgentRuntimeType",
    "AcpSessionMode",
    "AgentVerboseLevel",
    "AgentReasoningDefault",
    "SubagentDelegationMode",
    "AgentRuntimeAcpConfig",
    "AgentRuntimeConfig",
    "AgentBindingMatch",
    "AgentRouteBinding",
    "AgentAcpBinding",
    "AgentBinding",
    "AgentConfig",
    "AgentsConfig",
]
