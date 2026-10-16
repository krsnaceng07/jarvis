"""src.infra.exec_approvals_types - TypedDicts for exec approvals config schema.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-approvals.ts``
"""

from typing import Literal, TypedDict

from src.infra.exec_approvals import ExecAsk, ExecSecurity


class ExecAllowlistEntry(TypedDict, total=False):
    id: str
    pattern: str
    source: Literal["allow-always"]
    commandText: str
    argPattern: str
    lastUsedAt: int
    lastUsedCommand: str
    lastResolvedPath: str


class ExecApprovalsDefaults(TypedDict, total=False):
    security: ExecSecurity
    ask: ExecAsk
    askFallback: ExecSecurity
    autoAllowSkills: bool


class ExecApprovalsAgent(ExecApprovalsDefaults, total=False):
    allowlist: list[ExecAllowlistEntry]


class ExecApprovalsSocketConfig(TypedDict, total=False):
    path: str
    token: str


class ExecApprovalsFile(TypedDict, total=False):
    version: Literal[1]
    socket: ExecApprovalsSocketConfig
    defaults: ExecApprovalsDefaults
    agents: dict[str, ExecApprovalsAgent]


class ExecApprovalsSnapshot(TypedDict):
    path: str
    exists: bool
    raw: str | None
    file: ExecApprovalsFile
    hash: str


class ExecApprovalsAgentSources(TypedDict):
    security: str | None
    ask: str | None
    askFallback: str | None


class ExecApprovalsDefaultsRequired(TypedDict):
    security: ExecSecurity
    ask: ExecAsk
    askFallback: ExecSecurity
    autoAllowSkills: bool


class ExecApprovalsResolved(TypedDict):
    path: str
    socketPath: str
    token: str
    defaults: ExecApprovalsDefaultsRequired
    agent: ExecApprovalsDefaultsRequired
    agentSources: ExecApprovalsAgentSources
    allowlist: list[ExecAllowlistEntry]
    file: ExecApprovalsFile


class ExecApprovalsDefaultOverrides(TypedDict, total=False):
    security: ExecSecurity
    ask: ExecAsk
    askFallback: ExecSecurity
    autoAllowSkills: bool
    requireSocket: bool
