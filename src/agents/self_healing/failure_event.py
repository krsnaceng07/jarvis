"""src.agents.self_healing.failure_event — Standardized failure representation.

OpenClaw parity: mirrors failure signals, failover reasons, and execution
outcome classifications from packages/ai, packages/gateway-protocol, and
packages/agent-core.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal

SeverityLevel = Literal["transient", "recoverable", "degraded", "fatal"]


class ErrorCategory(str, Enum):
    """Closed error categories for deterministic self-healing decisions."""

    NETWORK_TRANSIENT = "network_transient"
    RATE_LIMIT = "rate_limit"
    AUTH_EXPIRED = "auth_expired"
    AUTH_PERMANENT = "auth_permanent"
    MODEL_OVERLOADED = "model_overloaded"
    CONTEXT_OVERFLOW = "context_overflow"
    TOOL_VALIDATION_ERROR = "tool_validation_error"
    TOOL_EXECUTION_ERROR = "tool_execution_error"
    TOOL_TIMEOUT = "tool_timeout"
    SYSTEM_IO_ERROR = "system_io_error"
    PROCESS_CRASH = "process_crash"
    INVALID_STATE = "invalid_state"
    EMPTY_RESPONSE = "empty_response"
    REASONING_ONLY = "reasoning_only"
    BILLING_EXHAUSTED = "billing_exhausted"
    TLS_CERTIFICATE_ERROR = "tls_certificate_error"
    MODEL_NOT_FOUND = "model_not_found"
    FORMAT_ERROR = "format_error"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN = "unknown"


def compute_failure_signature(
    category: ErrorCategory | str,
    source: str,
    error_snippet: str,
    target: str = "",
) -> str:
    """Compute a deterministic SHA256 signature for a failure.

    Used by the LoopPreventionEngine to detect repeating failure patterns
    and prevent infinite retry loops.
    """
    cat_str = category.value if isinstance(category, ErrorCategory) else str(category)
    norm_source = (source or "").strip().lower()
    norm_err = (error_snippet or "").strip().lower()[:120]
    norm_target = (target or "").strip().lower()
    raw = f"{cat_str}:{norm_source}:{norm_err}:{norm_target}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class FailureEvent:
    """Standardized machine-readable failure event across all JARVIS subsystems."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    category: ErrorCategory = ErrorCategory.UNKNOWN
    severity: SeverityLevel = "recoverable"
    error_message: str = ""
    exception_type: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    attempt_count: int = 1
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.signature:
            source = str(self.context.get("tool_name") or self.context.get("source") or "unknown")
            target = str(self.context.get("path") or self.context.get("target") or "")
            sig = compute_failure_signature(
                category=self.category,
                source=source,
                error_snippet=self.error_message,
                target=target,
            )
            object.__setattr__(self, "signature", sig)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d


__all__ = [
    "ErrorCategory",
    "FailureEvent",
    "SeverityLevel",
    "compute_failure_signature",
]
