"""jarvis.config.zod_schema_approvals — command approval Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.approvals.ts``.

Focused minimal port: schema definitions exposed as Python type stubs.
The actual zod-runtime validation is delegated to caller-provided
callables until the schema validator lands.
"""
from __future__ import annotations

from typing import Any


#: Native exec approval mode accepted by config.
NativeExecApprovalEnableModeSchema: Any = None  # z.union([z.boolean(), z.literal("auto")])


#: Schema for a single forwarding target.
ExecApprovalForwardTargetSchema: Any = None  # z.object({...}).strict()


#: Schema for exec / plugin approval forwarding config.
ExecApprovalForwardingSchema: Any = None  # z.object({...}).strict().optional()


#: Top-level approvals config schema.
ApprovalsSchema: Any = None  # z.object({exec, plugin}).strict().optional()


def native_exec_approval_enable_mode_validator(value: Any) -> bool:
    """Validate a native exec approval enable-mode value (bool or "auto")."""
    return isinstance(value, bool) or value == "auto"


__all__ = [
    "NativeExecApprovalEnableModeSchema",
    "ExecApprovalForwardTargetSchema",
    "ExecApprovalForwardingSchema",
    "ApprovalsSchema",
    "native_exec_approval_enable_mode_validator",
]
