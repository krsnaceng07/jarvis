"""Data types, error codes, and models for 1Password plugin.

OpenClaw parity: mirrors @openclaw/onepassword types, closed error
codes, policy tiers, and audit row shapes.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

# ── Closed Error Codes ────────────────────────────────────────────────────────

# 1Password access error codes
TOKEN_MISSING = "TOKEN_MISSING"
OP_NOT_FOUND = "OP_NOT_FOUND"
ITEM_NOT_FOUND = "ITEM_NOT_FOUND"
FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
RATE_LIMITED = "RATE_LIMITED"
AUTH_FAILED = "AUTH_FAILED"
TIMEOUT = "TIMEOUT"
OP_ERROR = "OP_ERROR"

# Policy and validation error codes
INVALID_ACTION = "INVALID_ACTION"
INVALID_REASON = "INVALID_REASON"
INVALID_SLUG = "INVALID_SLUG"
UNKNOWN_SLUG = "UNKNOWN_SLUG"
TOOL_CALL_ID_MISSING = "TOOL_CALL_ID_MISSING"
POLICY_NOT_EVALUATED = "POLICY_NOT_EVALUATED"
POLICY_CHANGED = "POLICY_CHANGED"
GRANT_EXPIRED = "GRANT_EXPIRED"
APPROVAL_CANCELLED = "APPROVAL_CANCELLED"

ALL_ERROR_CODES = {
    TOKEN_MISSING,
    OP_NOT_FOUND,
    ITEM_NOT_FOUND,
    FIELD_NOT_FOUND,
    RATE_LIMITED,
    AUTH_FAILED,
    TIMEOUT,
    OP_ERROR,
    INVALID_ACTION,
    INVALID_REASON,
    INVALID_SLUG,
    UNKNOWN_SLUG,
    TOOL_CALL_ID_MISSING,
    POLICY_NOT_EVALUATED,
    POLICY_CHANGED,
    GRANT_EXPIRED,
    APPROVAL_CANCELLED,
}

PolicyTier = Literal["auto", "approve", "deny"]
ApprovalDecision = Literal["allow_once", "allow_always", "deny"]
AuditOutcome = Literal["allowed", "denied", "error"]


@dataclass(frozen=True, slots=True)
class AuditRow:
    """Row recorded in SQLite onepassword_audit_log."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    agent_id: str = ""
    slug: str = ""
    action: str = ""
    outcome: AuditOutcome = "allowed"
    error_code: str | None = None
    reason: str = ""
    cached: bool = False
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "slug": self.slug,
            "action": self.action,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "reason": self.reason,
            "cached": self.cached,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class StandingGrant:
    """Persistent standing grant recorded in SQLite onepassword_grants."""

    agent_id: str
    slug: str
    granted_at: float
    expires_at: float
    last_used_at: float = field(default_factory=time.time)

    def is_valid(self, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        return current_time <= self.expires_at


@dataclass(frozen=True, slots=True)
class SecretItemResult:
    """Successful fetched secret result."""

    slug: str
    item: str
    field: str
    value: str


@dataclass(frozen=True, slots=True)
class SecretRefResolution:
    """Result of SecretRef resolution."""

    ref_id: str
    value: str | None = None
    cached: bool = False
    error: str | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationNonce:
    """Single-use authorization nonce handed between policy and tool execution."""

    nonce: str
    agent_id: str
    slug: str
    created_at: float
    expires_at: float

    def is_valid(self, now: float | None = None) -> bool:
        current_time = time.time() if now is None else now
        return current_time <= self.expires_at
