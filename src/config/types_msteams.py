"""jarvis.config.types_msteams — Microsoft Teams channel config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.msteams.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Teams SDK cloud environment.
MSTeamsCloudName = Literal["Public", "USGov", "USGovDoD", "China"]
#: Reply style for MS Teams messages.
MSTeamsReplyStyle = Literal["thread", "top-level"]


class MSTeamsWebhookConfig(TypedDict, total=False):
    port: int
    path: str


class MSTeamsSsoConfig(TypedDict, total=False):
    enabled: bool
    connectionName: str


class MSTeamsChannelConfig(TypedDict, total=False):
    requireMention: bool
    tools: dict
    toolsBySender: dict
    replyStyle: str


class MSTeamsTeamConfig(TypedDict, total=False):
    requireMention: bool
    tools: dict
    toolsBySender: dict
    replyStyle: str
    channels: dict


class MSTeamsConfig(TypedDict, total=False):
    enabled: bool
    capabilities: list
    dangerouslyAllowNameMatching: bool
    markdown: dict
    configWrites: bool
    appId: str
    appPassword: object
    tenantId: str
    cloud: str
    webhook: MSTeamsWebhookConfig
    sso: MSTeamsSsoConfig
    requireMention: bool
    groupPolicy: str
    groupAllowFrom: list
    defaultTo: str
    historyLimit: int
    dmHistoryLimit: int
    dms: dict
    textChunkLimit: int
    streaming: dict
    mediaMaxMb: int
    replyToMode: str
    healthMonitor: dict
    heartbeat: dict
    typingIndicator: str
    responsePrefix: str
    teams: dict
    accounts: dict
    defaultAccount: str
    # Top-level mirrored fields
    name: str


__all__ = [
    "MSTeamsCloudName",
    "MSTeamsReplyStyle",
    "MSTeamsWebhookConfig",
    "MSTeamsSsoConfig",
    "MSTeamsChannelConfig",
    "MSTeamsTeamConfig",
    "MSTeamsConfig",
]
