"""jarvis_learning.evaluation.attribution — classified failure attribution and rollback hysteresis.

Implements:
- INV-HEALTH-001: 7-cause classified attribution evidence chain
- INV-HEALTH-002: Rollback hysteresis and flapping prevention controller
- INV-HEALTH-003: Unknown attribution safety handling (pause rollback, alert operator)
- INV-RBK-001: Deterministic known-good rollback target and safe degraded mode
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Sequence

logger = logging.getLogger(__name__)


class FailureCause(str, Enum):
    """Formal failure attribution classes."""

    MODEL_CAUSED = "model_caused"
    CONFIRMED_MODEL_CAUSED = "confirmed_model_caused"
    PROBABLE_MODEL_CAUSED = "probable_model_caused"
    ENVIRONMENT_CAUSED = "environment_caused"
    USER_INPUT_CAUSED = "user_input_caused"
    EXTERNAL_SERVICE = "external_service"
    TOOL_IMPLEMENTATION = "tool_implementation"
    TOOL_CAUSED = "tool_caused"
    POLICY_BLOCKED = "policy_blocked"
    UNKNOWN_INCONCLUSIVE = "unknown_inconclusive"


@dataclass(frozen=True, slots=True)
class FailureAttributionEvidence:
    """Root-cause evidence chain for execution failures.

    Enforces INV-HEALTH-001.
    """

    primary_cause: FailureCause
    confidence: float
    evidence_signals: tuple[str, ...]
    is_reproducible: bool = False
    reproduced_in_baseline: bool = False
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class FailureAttributionEngine:
    """Classifies failures across the 7 causes using deterministic signal patterns.

    Enforces INV-HEALTH-001 & INV-HEALTH-003.
    """

    # Keyword patterns for signals
    _EXTERNAL_KEYWORDS = (
        "network",
        "connection reset",
        "timeout",
        "timed out",
        "dns",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
        "econnrefused",
        "socket error",
        "http 5",
    )
    _TOOL_IMPL_KEYWORDS = (
        "typeerror",
        "attributeerror",
        "indexerror",
        "keyerror",
        "zerodivisionerror",
        "unhandled exception in tool",
        "stack trace",
        "import error",
    )
    _POLICY_KEYWORDS = (
        "policy blocked",
        "permission denied",
        "unauthorized",
        "destructive action disallowed",
        "forbidden action",
        "security violation",
        "approval required",
    )
    _USER_INPUT_KEYWORDS = (
        "ambiguous prompt",
        "user cancellation",
        "contradictory instruction",
        "user correction",
        "invalid syntax from user",
        "malformed user command",
    )
    _ENVIRONMENT_KEYWORDS = (
        "disk full",
        "no space left on device",
        "file not found on disk",
        "os error",
        "process died unexpectedly",
        "resource temporarily unavailable",
        "memory allocation failed at os level",
    )
    _MODEL_KEYWORDS = (
        "hallucinated tool",
        "invalid arguments generated",
        "schema validation failed for tool args",
        "false completion claim",
        "incorrect tool selection",
        "infinite repetition",
        "contradictory state claim",
    )

    def attribute(
        self,
        *,
        error_message: str,
        tool_name: str = "",
        exit_code: int | None = None,
        traceback_str: str = "",
        is_reproducible: bool = False,
        reproduced_in_baseline: bool = False,
        extra_signals: Sequence[str] | None = None,
    ) -> FailureAttributionEvidence:
        """Classify failure root cause based on error message, traces, and execution context."""
        text = f"{error_message} {traceback_str}".lower()
        signals: list[str] = list(extra_signals or [])

        # Check external service outage
        for kw in self._EXTERNAL_KEYWORDS:
            if kw in text:
                signals.append(f"matched external keyword: '{kw}'")
        if signals and any("external" in s for s in signals):
            return FailureAttributionEvidence(
                primary_cause=FailureCause.EXTERNAL_SERVICE,
                confidence=0.95,
                evidence_signals=tuple(signals),
                is_reproducible=is_reproducible,
                reproduced_in_baseline=reproduced_in_baseline,
            )

        # Check tool implementation bug
        for kw in self._TOOL_IMPL_KEYWORDS:
            if kw in text:
                signals.append(f"matched tool bug keyword: '{kw}'")
        if signals and any("tool bug" in s for s in signals):
            return FailureAttributionEvidence(
                primary_cause=FailureCause.TOOL_IMPLEMENTATION,
                confidence=0.90,
                evidence_signals=tuple(signals),
                is_reproducible=is_reproducible,
                reproduced_in_baseline=reproduced_in_baseline,
            )

        # Check policy block
        for kw in self._POLICY_KEYWORDS:
            if kw in text:
                signals.append(f"matched policy keyword: '{kw}'")
        if signals and any("policy" in s for s in signals):
            return FailureAttributionEvidence(
                primary_cause=FailureCause.POLICY_BLOCKED,
                confidence=0.98,
                evidence_signals=tuple(signals),
                is_reproducible=is_reproducible,
                reproduced_in_baseline=reproduced_in_baseline,
            )

        # Check user input defect
        for kw in self._USER_INPUT_KEYWORDS:
            if kw in text:
                signals.append(f"matched user input keyword: '{kw}'")
        if signals and any("user input" in s for s in signals):
            return FailureAttributionEvidence(
                primary_cause=FailureCause.USER_INPUT_CAUSED,
                confidence=0.90,
                evidence_signals=tuple(signals),
                is_reproducible=is_reproducible,
                reproduced_in_baseline=reproduced_in_baseline,
            )

        # Check OS/environment outage
        for kw in self._ENVIRONMENT_KEYWORDS:
            if kw in text:
                signals.append(f"matched environment keyword: '{kw}'")
        if signals and any("environment" in s for s in signals):
            return FailureAttributionEvidence(
                primary_cause=FailureCause.ENVIRONMENT_CAUSED,
                confidence=0.85,
                evidence_signals=tuple(signals),
                is_reproducible=is_reproducible,
                reproduced_in_baseline=reproduced_in_baseline,
            )

        # Check model caused
        for kw in self._MODEL_KEYWORDS:
            if kw in text:
                signals.append(f"matched model failure keyword: '{kw}'")
        if signals and any("model failure" in s for s in signals):
            return FailureAttributionEvidence(
                primary_cause=FailureCause.MODEL_CAUSED,
                confidence=0.95,
                evidence_signals=tuple(signals),
                is_reproducible=is_reproducible,
                reproduced_in_baseline=reproduced_in_baseline,
            )

        # If error reproduced in baseline, it's environmental or service-related
        if reproduced_in_baseline:
            signals.append("failure reproduced in last-known-good baseline")
            return FailureAttributionEvidence(
                primary_cause=FailureCause.ENVIRONMENT_CAUSED,
                confidence=0.80,
                evidence_signals=tuple(signals),
                is_reproducible=is_reproducible,
                reproduced_in_baseline=True,
            )

        # If completely ambiguous, return UNKNOWN_INCONCLUSIVE
        signals.append("no decisive signal detected in error or traceback")
        return FailureAttributionEvidence(
            primary_cause=FailureCause.UNKNOWN_INCONCLUSIVE,
            confidence=0.40,
            evidence_signals=tuple(signals),
            is_reproducible=is_reproducible,
            reproduced_in_baseline=reproduced_in_baseline,
        )


@dataclass(frozen=True, slots=True)
class RollbackDecision:
    """Actionable decision output from the hysteresis and health controller."""

    rollback_triggered: bool
    target_model_id: str | None
    is_safe_degraded_mode: bool
    paused_for_operator_inspection: bool
    alert_message: str
    reasons: tuple[str, ...]


class RollbackHysteresisController:
    """Manages rollback triggers, cooldown windows, anti-flapping, and known-good targets.

    Enforces INV-HEALTH-002, INV-HEALTH-003, INV-RBK-001.
    """

    def __init__(
        self,
        *,
        cooldown_window_seconds: float = 86400.0,  # 24-hour hysteresis
        max_consecutive_model_failures: int = 3,
        window_size: int = 30,
        max_model_error_rate: float = 0.10,
    ) -> None:
        self.cooldown_window_seconds = cooldown_window_seconds
        self.max_consecutive = max_consecutive_model_failures
        self.window_size = window_size
        self.max_error_rate = max_model_error_rate

        self._recent_events: deque[tuple[float, FailureAttributionEvidence, bool]] = deque(
            maxlen=window_size
        )
        self._last_rollback_time: float = 0.0
        self._last_promoted_model_id: str | None = None
        self._rollback_history: list[dict[str, Any]] = []

    def register_promotion(self, model_id: str, timestamp: float | None = None) -> None:
        """Record model promotion event."""
        self._last_promoted_model_id = model_id

    def record_execution_outcome(
        self,
        evidence: FailureAttributionEvidence,
        is_critical_safety: bool = False,
        timestamp: float | None = None,
        last_known_good_model_id: str | None = None,
        known_good_is_valid: bool = True,
    ) -> RollbackDecision:
        """Evaluate incoming failure evidence and determine whether to trigger rollback or pause."""
        now = timestamp if timestamp is not None else time.time()
        self._recent_events.append((now, evidence, is_critical_safety))

        reasons: list[str] = []

        # 1. Critical safety violations trigger immediate rollback (INV-HEALTH-001)
        if is_critical_safety:
            reasons.append("CRITICAL SAFETY VIOLATION detected in active model execution")

        # 2. Unknown inconclusive handling (INV-HEALTH-003)
        if evidence.primary_cause == FailureCause.UNKNOWN_INCONCLUSIVE:
            # Pauses automatic rollback and requests operator inspection
            alert_msg = (
                f"UNKNOWN_INCONCLUSIVE failure detected: signals={evidence.evidence_signals}. "
                "Automatic rollback paused pending operator diagnostic inspection."
            )
            return RollbackDecision(
                rollback_triggered=False,
                target_model_id=None,
                is_safe_degraded_mode=False,
                paused_for_operator_inspection=True,
                alert_message=alert_msg,
                reasons=("unknown_inconclusive_pause",),
            )

        # 3. Sliding window check for model-caused failures
        model_failures = [
            ev
            for (_, ev, is_crit) in self._recent_events
            if ev.primary_cause == FailureCause.MODEL_CAUSED or is_crit
        ]
        consecutive_model_failures = 0
        for _, ev, is_crit in reversed(self._recent_events):
            if ev.primary_cause == FailureCause.MODEL_CAUSED or is_crit:
                consecutive_model_failures += 1
            else:
                break

        if consecutive_model_failures >= self.max_consecutive:
            reasons.append(
                f"Consecutive model-caused failures ({consecutive_model_failures}) >= threshold ({self.max_consecutive})"
            )

        total_in_window = len(self._recent_events)
        if total_in_window >= 5:
            err_rate = len(model_failures) / total_in_window
            if err_rate > self.max_error_rate:
                reasons.append(
                    f"Model-caused error rate ({err_rate:.2f}) > threshold ({self.max_error_rate:.2f})"
                )

        if not reasons:
            return RollbackDecision(
                rollback_triggered=False,
                target_model_id=None,
                is_safe_degraded_mode=False,
                paused_for_operator_inspection=False,
                alert_message="",
                reasons=(),
            )

        # 4. Anti-flapping and Cooldown check (INV-HEALTH-002)
        elapsed_since_last_rollback = now - self._last_rollback_time
        if (
            self._last_rollback_time > 0
            and elapsed_since_last_rollback < self.cooldown_window_seconds
        ):
            # Within cooldown window - alert operator to prevent flapping loop
            alert_msg = (
                f"Rollback triggered but blocked by anti-flapping hysteresis "
                f"({elapsed_since_last_rollback:.0f}s < {self.cooldown_window_seconds:.0f}s cooldown). "
                "Operator intervention required."
            )
            return RollbackDecision(
                rollback_triggered=False,
                target_model_id=None,
                is_safe_degraded_mode=False,
                paused_for_operator_inspection=True,
                alert_message=alert_msg,
                reasons=tuple(reasons),
            )

        # 5. Deterministic target selection (INV-RBK-001)
        self._last_rollback_time = now
        if last_known_good_model_id and known_good_is_valid:
            target_id = last_known_good_model_id
            is_degraded = False
            msg = f"Rollback triggered to known-good model '{target_id}': {'; '.join(reasons)}"
        else:
            # Known-good is unavailable, corrupt, or revoked -> SAFE_DEGRADED_MODE
            target_id = None
            is_degraded = True
            msg = f"Rollback triggered but known-good model is unavailable/invalid. Entering SAFE_DEGRADED_MODE: {'; '.join(reasons)}"

        return RollbackDecision(
            rollback_triggered=True,
            target_model_id=target_id,
            is_safe_degraded_mode=is_degraded,
            paused_for_operator_inspection=False,
            alert_message=msg,
            reasons=tuple(reasons),
        )
