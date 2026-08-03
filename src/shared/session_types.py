"""jarvis.shared.session_types — session listing response types.

OpenClaw parity: mirrors ``openclaw-main/src/shared/session-types.ts``.
"""
from __future__ import annotations

from typing import Generic, List, Optional, TypedDict, TypeVar

TDefaults = TypeVar("TDefaults")
TRow = TypeVar("TRow")
TEntry = TypeVar("TEntry")


class GatewayAgentIdentity(TypedDict, total=False):
    name: str
    theme: str
    emoji: str
    avatar: str
    avatarUrl: str


class GatewayAgentModel(TypedDict, total=False):
    primary: str
    fallbacks: List[str]


class GatewayAgentRuntime(TypedDict, total=False):
    id: str
    fallback: str  # "openclaw" | "none"
    source: str  # "env" | "agent" | "defaults" | "model" | "provider" | "implicit" | "session" | "session-key"


class GatewayThinkingLevelOption(TypedDict, total=False):
    id: str
    label: str


class GatewayAgentRow(TypedDict, total=False):
    id: str
    name: str
    identity: GatewayAgentIdentity
    workspace: str
    workspaceGit: bool
    model: GatewayAgentModel
    agentRuntime: GatewayAgentRuntime
    thinkingLevels: List[GatewayThinkingLevelOption]
    thinkingOptions: List[str]
    thinkingDefault: str


class SessionsListResultBase(TypedDict, Generic[TDefaults, TRow], total=False):
    ts: int
    path: str
    count: int
    totalCount: int
    limitApplied: int
    offset: int
    nextOffset: int
    hasMore: bool
    defaults: TDefaults
    sessions: List[TRow]


class SessionsPatchResultBase(TypedDict, Generic[TEntry], total=False):
    ok: bool
    path: str
    key: str
    entry: TEntry


__all__ = [
    "GatewayAgentIdentity",
    "GatewayAgentModel",
    "GatewayAgentRuntime",
    "GatewayThinkingLevelOption",
    "GatewayAgentRow",
    "SessionsListResultBase",
    "SessionsPatchResultBase",
]
