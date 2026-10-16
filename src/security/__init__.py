"""jarvis.security — Comprehensive production security architecture.

Matches OpenClaw security architecture, logic, pipeline, and behavior.
"""

from __future__ import annotations

from .policy_engine import (
    Capability,
    PolicyDecision,
    RiskLevel,
    SecurityPolicyEngine,
    SecurityPrincipal,
    TrustLevel,
)
from .filesystem_guard import FilesystemGuard, SecurityViolationError
from .exec_guard import CommandValidationResult, ExecGuard
from .secret_redactor import SecretRedactor
from .prompt_trust import TrustBoundaryTagger
from .audit_logger import SecurityAuditEvent, SecurityAuditLogger

__all__ = [
    "Capability",
    "PolicyDecision",
    "RiskLevel",
    "SecurityPolicyEngine",
    "SecurityPrincipal",
    "TrustLevel",
    "FilesystemGuard",
    "SecurityViolationError",
    "CommandValidationResult",
    "ExecGuard",
    "SecretRedactor",
    "TrustBoundaryTagger",
    "SecurityAuditEvent",
    "SecurityAuditLogger",
]
