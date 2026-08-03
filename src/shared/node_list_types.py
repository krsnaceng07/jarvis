"""jarvis.shared.node_list_types — node-list payload types.

OpenClaw parity: mirrors ``openclaw-main/src/shared/node-list-types.ts``.
"""
from __future__ import annotations

from typing import List, Optional, TypedDict


class NodeListNode(TypedDict, total=False):
    """Node record returned by gateway node-list endpoints.

    Mirrors :type:`NodeListNode` (``shared/node-list-types.ts``).
    """
    nodeId: str
    displayName: str
    platform: str
    version: str
    coreVersion: str
    uiVersion: str
    clientId: str
    clientMode: str
    remoteIp: str
    deviceFamily: str
    modelIdentifier: str
    pathEnv: str
    caps: List[str]
    commands: List[str]
    permissions: dict
    approvalState: str  # "approved" | "pending-approval" | "pending-reapproval" | "unapproved"
    pendingRequestId: str
    pendingDeclaredCaps: List[str]
    pendingDeclaredCommands: List[str]
    pendingDeclaredPermissions: dict
    paired: bool
    connected: bool
    connectedAtMs: int
    lastActiveAtMs: int
    presenceUpdatedAtMs: int
    active: bool
    lastSeenAtMs: int
    lastSeenReason: str
    approvedAtMs: int


class PendingRequest(TypedDict, total=False):
    """Pending pairing/access request shown to operators.

    Mirrors :type:`PendingRequest` (``shared/node-list-types.ts``).
    """
    requestId: str
    nodeId: str
    displayName: str
    platform: str
    version: str
    coreVersion: str
    uiVersion: str
    remoteIp: str
    ts: int
    commands: List[str]
    requiredApproveScopes: List[str]  # "operator.pairing" | "operator.write" | "operator.admin"


class PairedNode(TypedDict, total=False):
    """Persisted paired node entry with permission metadata.

    Mirrors :type:`PairedNode` (``shared/node-list-types.ts``).
    """
    nodeId: str
    displayName: str
    platform: str
    version: str
    coreVersion: str
    uiVersion: str
    remoteIp: str
    permissions: dict
    createdAtMs: int
    approvedAtMs: int
    lastConnectedAtMs: int
    lastSeenAtMs: int
    lastSeenReason: str


class PairingList(TypedDict, total=False):
    """Combined pairing list result for CLI/UI node approval surfaces.

    Mirrors :type:`PairingList` (``shared/node-list-types.ts``).
    """
    pending: List[PendingRequest]
    paired: List[PairedNode]


__all__ = ["NodeListNode", "PendingRequest", "PairedNode", "PairingList"]
