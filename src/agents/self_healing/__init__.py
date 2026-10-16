"""src.agents.self_healing — Self-Healing & Self-Recovery architecture.

OpenClaw parity: autonomous failure detection, error taxonomy classification,
loop-prevented recovery decision engine, real-state verification, persistent
audit ledger, and anti-hallucination truthful escalation.
"""

from __future__ import annotations

from .audit_ledger import RecoveryAuditLedger
from .classifier import ErrorClassifier
from .decision_engine import (
    EMPTY_RESPONSE_RETRY_INSTRUCTION,
    REASONING_ONLY_RETRY_INSTRUCTION,
    SETTLED_TOOL_TERMINAL_CONTINUATION_INSTRUCTION,
    RecoveryAction,
    RecoveryDecision,
    RecoveryDecisionEngine,
)
from .failure_event import (
    ErrorCategory,
    FailureEvent,
    SeverityLevel,
    compute_failure_signature,
)
from .last_verified_state import LastVerifiedState, VerifiedActionRecord
from .loop_prevention import (
    DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT,
    DEFAULT_REASONING_ONLY_RETRY_LIMIT,
    LoopPreventionEngine,
)
from .strategies import (
    MODEL_FAILOVER_CHAIN,
    PARAM_ALIASES,
    ProviderFallbackStrategy,
    RecoveryResult,
    RecoveryStrategy,
    ToolArgumentRepairStrategy,
    ToolFallbackStrategy,
    TransientRetryStrategy,
)
from .truthful_escalator import TruthfulEscalationFormatter

__all__ = [
    "DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT",
    "DEFAULT_REASONING_ONLY_RETRY_LIMIT",
    "EMPTY_RESPONSE_RETRY_INSTRUCTION",
    "ErrorCategory",
    "ErrorClassifier",
    "FailureEvent",
    "LastVerifiedState",
    "LoopPreventionEngine",
    "MODEL_FAILOVER_CHAIN",
    "PARAM_ALIASES",
    "ProviderFallbackStrategy",
    "REASONING_ONLY_RETRY_INSTRUCTION",
    "RecoveryAction",
    "RecoveryAuditLedger",
    "RecoveryDecision",
    "RecoveryDecisionEngine",
    "RecoveryResult",
    "RecoveryStrategy",
    "SETTLED_TOOL_TERMINAL_CONTINUATION_INSTRUCTION",
    "SeverityLevel",
    "ToolArgumentRepairStrategy",
    "ToolFallbackStrategy",
    "TransientRetryStrategy",
    "TruthfulEscalationFormatter",
    "VerifiedActionRecord",
    "compute_failure_signature",
]
