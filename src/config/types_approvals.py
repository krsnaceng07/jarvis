"""jarvis.config.types_approvals — command approval config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.approvals.ts``.
"""
from __future__ import annotations

from typing import TypedDict

#: Whether the native exec approval flow is enabled (auto = on-by-default).
NativeExecApprovalEnableMode = object  # bool | "auto"
#: Approval forwarding mode.
ExecApprovalForwardingMode = str  # "session" | "targets" | "both"


class ExecApprovalForwardTarget(TypedDict, total=False):
    channel: str
    to: str
    accountId: str
    threadId: object  # str | int


class ExecApprovalForwardingConfig(TypedDict, total=False):
    enabled: bool
    mode: str
    agentFilter: list
    sessionFilter: list
    targets: list


class ApprovalsConfig(TypedDict, total=False):
    exec: ExecApprovalForwardingConfig
    plugin: ExecApprovalForwardingConfig


__all__ = [
    "NativeExecApprovalEnableMode",
    "ExecApprovalForwardingMode",
    "ExecApprovalForwardTarget",
    "ExecApprovalForwardingConfig",
    "ApprovalsConfig",
]
