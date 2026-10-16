"""jarvis_sdk.plugin_approval — Plugin Permission Requests & Gateway Approval Flow.

OpenClaw parity: mirrors
``openclaw-main/docs/plugins/plugin-permission-requests.md`` and
``openclaw-main/src/infra/approval-errors.ts``.

Features:
- `PluginApprovalSeverity`: `"info"` | `"warning"` | `"critical"`
- `PluginApprovalDecision`: `"allow-once"` | `"allow-always"` | `"deny"` | `"timeout"` | `"cancelled"`
- `PluginApprovalRequest`: Dataclass holding approval request details with strict Gateway limits.
- `create_plugin_approval_request()`: Helper function creating validated approval requests.
- Error codes: `APPROVAL_NOT_FOUND`, `APPROVAL_ALREADY_RESOLVED`, `INVALID_REQUEST`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

PluginApprovalSeverity = Literal["info", "warning", "critical"]
PluginApprovalDecision = Literal["allow-once", "allow-always", "deny", "timeout", "cancelled"]

APPROVAL_NOT_FOUND = "APPROVAL_NOT_FOUND"
APPROVAL_ALREADY_RESOLVED = "APPROVAL_ALREADY_RESOLVED"
INVALID_REQUEST = "INVALID_REQUEST"


@dataclass
class PluginApprovalRequest:
    title: str
    description: str
    severity: PluginApprovalSeverity = "warning"
    allowedDecisions: list[PluginApprovalDecision] = field(
        default_factory=lambda: ["allow-once", "allow-always", "deny"]
    )
    timeoutMs: int = 120000
    onResolution: Callable[[PluginApprovalDecision], Any] | None = None

    def __post_init__(self) -> None:
        # Enforce Gateway character caps & timeout limits
        if len(self.title) > 80:
            self.title = self.title[:80]
        if len(self.description) > 512:
            self.description = self.description[:512]
        if self.timeoutMs <= 0:
            self.timeoutMs = 120000
        elif self.timeoutMs > 600000:
            self.timeoutMs = 600000


def create_plugin_approval_request(
    title: str,
    description: str,
    severity: PluginApprovalSeverity = "warning",
    allowed_decisions: list[PluginApprovalDecision] | None = None,
    timeout_ms: int = 120000,
    on_resolution: Callable[[PluginApprovalDecision], Any] | None = None,
) -> PluginApprovalRequest:
    """Create a validated plugin permission approval request."""
    from typing import cast as _cast

    decisions: list[PluginApprovalDecision] = (
        allowed_decisions
        if allowed_decisions
        else _cast(list[PluginApprovalDecision], ["allow-once", "allow-always", "deny"])
    )
    return PluginApprovalRequest(
        title=title,
        description=description,
        severity=severity,
        allowedDecisions=decisions,
        timeoutMs=timeout_ms,
        onResolution=on_resolution,
    )


class PluginApprovalError(Exception):
    """Exception raised for approval routing or decision failures."""

    def __init__(self, message: str, code: str = INVALID_REQUEST) -> None:
        super().__init__(message)
        self.code = code


__all__ = [
    "APPROVAL_ALREADY_RESOLVED",
    "APPROVAL_NOT_FOUND",
    "INVALID_REQUEST",
    "PluginApprovalDecision",
    "PluginApprovalError",
    "PluginApprovalRequest",
    "PluginApprovalSeverity",
    "create_plugin_approval_request",
]
