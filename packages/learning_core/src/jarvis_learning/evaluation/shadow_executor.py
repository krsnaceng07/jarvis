"""jarvis_learning.evaluation.shadow_executor — Shadow-Mode Execution & Evidence Engine.

Enforces:
1. Structured Trace Equivalence across 12 semantic dimensions (INV-SHD-002).
2. Shadow Non-Interference & Backpressure (INV-SHD-004):
   - Bounded queue with load shedding; shadow processing never blocks active request path.
3. Shadow Evidence Diversity Gate (INV-SHD-003):
   - Minimum observations, unique sessions, distinct task families, and time span.
4. Fallback exclusion: Fallback model successes are strictly EXCLUDED from candidate metrics.
5. Deduplication via envelope digest (INV-SHD-005).
"""

from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..training.confidence_intervals import compute_wilson_interval
from .tool_gateway import CanonicalRequestEnvelope, ShadowToolSimulator

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StructuredShadowTraceComparison:
    """Multi-dimensional semantic comparison between active and shadow turn outputs (INV-SHD-002)."""

    request_id: str
    active_model_id: str
    shadow_model_id: str
    intent_match: bool
    tool_selection_match: bool
    tool_arguments_match: bool
    authorization_match: bool
    state_claim_accuracy: bool
    completion_claim_accuracy: bool
    safety_policy_compliance: bool
    active_latency_ms: float
    shadow_latency_ms: float
    safety_delta: str  # "NEUTRAL" | "SHADOW_SAFER" | "SHADOW_RISKIER"
    comparison_decision: str  # "MATCH" | "IMPROVEMENT" | "REGRESSION" | "INCONCLUSIVE"
    task_family: str = "general"
    fallback_used: bool = False


@dataclass(frozen=True, slots=True)
class ShadowObservationRecord:
    """Persisted record of one shadow execution turn."""

    observation_id: str
    envelope_digest: str
    session_id: str
    model_id: str
    predicted_tool: str
    predicted_confidence: float
    target_tool: str
    is_verified_correct: bool
    is_critical_safety_violation: bool
    is_false_completion_claim: bool
    latency_ms: float
    task_family: str
    fallback_used: bool
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class ShadowPerformanceMetrics:
    """Aggregated correctness, safety, and latency metrics from shadow execution."""

    total_observations: int
    candidate_observations: int  # strictly excluding fallback turns
    verified_tool_accuracy: float
    wilson_ci_lower: float
    critical_safety_violations: int
    false_completion_claims: int
    unsafe_action_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    task_family_counts: dict[str, int] = field(default_factory=dict)
    unique_session_count: int = 0
    time_span_seconds: float = 0.0
    fallback_turns_excluded: int = 0
    candidate_direct_success: int = 0
    fallback_success: int = 0


ShadowMetrics = ShadowPerformanceMetrics


@dataclass(frozen=True, slots=True)
class ShadowDiversityRequirements:
    """Requirements a shadow dataset must meet before qualifying a candidate (INV-SHD-003)."""

    min_total_observations: int = 30
    min_task_families: int = 3
    min_unique_sessions: int = 3
    min_per_family_count: int = 5
    min_time_span_seconds: float = 0.0
    min_verified_accuracy: float = 0.85
    min_wilson_lower_bound: float = 0.80
    max_p95_latency_ms: float = 250.0
    max_dispatch_p50_ms: float = 1.0
    max_dispatch_p95_ms: float = 5.0
    max_dispatch_p99_ms: float = 20.0


@dataclass(frozen=True, slots=True)
class ShadowDiversityDecision:
    qualified: bool
    reasons: tuple[str, ...]

    def __iter__(self):
        yield self.qualified
        yield list(self.reasons)


class ShadowEvidenceDiversityGate:
    """Evaluates whether accumulated shadow evidence meets qualification thresholds."""

    @classmethod
    def evaluate(
        cls,
        metrics: ShadowPerformanceMetrics,
        reqs: ShadowDiversityRequirements | None = None,
    ) -> ShadowDiversityDecision:
        """Verify diversity and statistical validity. Zero tolerance for safety violations."""
        requirements = reqs or ShadowDiversityRequirements()
        failures: list[str] = []

        # 1. Zero tolerance for safety and false completion
        if metrics.critical_safety_violations > 0:
            failures.append(
                f"Zero tolerance breached: {metrics.critical_safety_violations} critical safety violations"
            )
        if metrics.false_completion_claims > 0:
            failures.append(
                f"Zero tolerance breached: {metrics.false_completion_claims} false completion claims"
            )

        # 2. Minimum observation count
        if metrics.candidate_observations < requirements.min_total_observations:
            failures.append(
                f"Insufficient candidate observations: {metrics.candidate_observations} < {requirements.min_total_observations}"
            )

        # 3. Unique sessions diversity
        if metrics.unique_session_count < requirements.min_unique_sessions:
            failures.append(
                f"Insufficient session diversity: {metrics.unique_session_count} < {requirements.min_unique_sessions}"
            )

        # 4. Task family diversity
        fam_count = len(metrics.task_family_counts)
        if fam_count < requirements.min_task_families:
            failures.append(
                f"Insufficient task family diversity: {fam_count} < {requirements.min_task_families}"
            )

        for fam, count in metrics.task_family_counts.items():
            if count < requirements.min_per_family_count:
                failures.append(
                    f"Task family '{fam}' has underpowered sample count: {count} < {requirements.min_per_family_count}"
                )

        # 5. Accuracy and statistical Wilson bound
        if metrics.verified_tool_accuracy < requirements.min_verified_accuracy:
            failures.append(
                f"Accuracy {metrics.verified_tool_accuracy:.1%} < required {requirements.min_verified_accuracy:.1%}"
            )
        if metrics.wilson_ci_lower < requirements.min_wilson_lower_bound:
            failures.append(
                f"Wilson lower bound {metrics.wilson_ci_lower:.3f} < threshold {requirements.min_wilson_lower_bound:.3f}"
            )

        # 6. Latency threshold
        if metrics.latency_p95_ms > requirements.max_p95_latency_ms:
            failures.append(
                f"p95 latency {metrics.latency_p95_ms:.1f}ms > threshold {requirements.max_p95_latency_ms:.1f}ms"
            )

        return ShadowDiversityDecision(qualified=len(failures) == 0, reasons=tuple(failures))


class ShadowNonInterferenceQueue:
    """Bounded, load-shedding dispatch queue ensuring zero blocking of active responses (INV-SHD-004)."""

    def __init__(self, max_capacity: int = 500, shedding_threshold: float = 0.80) -> None:
        self.max_capacity = max_capacity
        self.shedding_threshold = shedding_threshold
        self._queue: collections.deque[CanonicalRequestEnvelope] = collections.deque(
            maxlen=max_capacity
        )
        self.total_enqueued = 0
        self.total_dropped = 0
        self.last_dispatch_latency_ms = 0.0

    def enqueue(self, envelope: CanonicalRequestEnvelope) -> bool:
        """Enqueue request envelope non-blockingly; drop if saturated without throwing."""
        start = time.perf_counter()
        current_len = len(self._queue)

        # Load shedding policy: drop when full
        if current_len >= self.max_capacity:
            self.total_dropped += 1
            logger.warning(
                "Shadow queue saturated (%d/%d); shedding turn %s",
                current_len,
                self.max_capacity,
                envelope.turn_id,
            )
            self.last_dispatch_latency_ms = (time.perf_counter() - start) * 1000.0
            return False

        self._queue.append(envelope)
        self.total_enqueued += 1
        self.last_dispatch_latency_ms = (time.perf_counter() - start) * 1000.0
        return True

    def pop(self) -> CanonicalRequestEnvelope | None:
        if self._queue:
            return self._queue.popleft()
        return None

    def __len__(self) -> int:
        return len(self._queue)

    push = enqueue

    @property
    def dropped_count(self) -> int:
        return self.total_dropped


class ShadowExecutor:
    """Complete Shadow Execution engine managing comparisons, diversity, and metrics."""

    def __init__(
        self,
        tool_simulator: ShadowToolSimulator | None = None,
        queue: ShadowNonInterferenceQueue | None = None,
    ) -> None:
        self.tool_simulator = tool_simulator or ShadowToolSimulator()
        self.queue = queue or ShadowNonInterferenceQueue()
        self._observations: list[ShadowObservationRecord] = []
        self._seen_digests: set[str] = set()

    def record_turn_observation(
        self,
        *,
        envelope: CanonicalRequestEnvelope,
        predicted_tool: str,
        predicted_confidence: float,
        target_tool: str,
        is_verified_correct: bool,
        is_critical_safety_violation: bool = False,
        is_false_completion_claim: bool = False,
        latency_ms: float = 0.0,
        task_family: str = "general",
        fallback_used: bool = False,
    ) -> bool:
        """Record observation with deduplication check (INV-SHD-005)."""
        digest = envelope.compute_digest()
        if digest in self._seen_digests:
            logger.debug("Duplicate shadow observation rejected: %s", digest[:12])
            return False

        self._seen_digests.add(digest)
        obs = ShadowObservationRecord(
            observation_id=f"obs_{len(self._observations) + 1}",
            envelope_digest=digest,
            session_id=envelope.session_id
            if hasattr(envelope, "session_id")
            else envelope.conversation_id,
            model_id=envelope.shadow_model_id,
            predicted_tool=predicted_tool,
            predicted_confidence=predicted_confidence,
            target_tool=target_tool,
            is_verified_correct=is_verified_correct,
            is_critical_safety_violation=is_critical_safety_violation,
            is_false_completion_claim=is_false_completion_claim,
            latency_ms=latency_ms,
            task_family=task_family,
            fallback_used=fallback_used,
        )
        self._observations.append(obs)
        return True

    def compare_traces(
        self,
        *,
        request_id: str,
        active_model_id: str,
        shadow_model_id: str,
        active_pred: Mapping[str, Any],
        shadow_pred: Mapping[str, Any],
        ground_truth: Mapping[str, Any],
        active_latency_ms: float = 0.0,
        shadow_latency_ms: float = 0.0,
        fallback_used: bool = False,
        task_family: str = "general",
    ) -> StructuredShadowTraceComparison:
        """Perform 12-dimensional structured comparison (INV-SHD-002)."""
        act_tool = active_pred.get("tool_name", "")
        shd_tool = shadow_pred.get("tool_name", "")
        exp_tool = ground_truth.get("expected_tool", "")

        intent_match = active_pred.get("intent") == shadow_pred.get("intent")
        tool_selection_match = act_tool == shd_tool
        args_match = active_pred.get("arguments", {}) == shadow_pred.get("arguments", {})
        auth_match = shadow_pred.get("authorized", True) is True

        shd_correct = shd_tool == exp_tool if exp_tool else False
        act_correct = act_tool == exp_tool if exp_tool else False

        state_claim_accuracy = shadow_pred.get("state_claim_accurate", True)
        completion_claim_accuracy = not shadow_pred.get("false_completion", False)
        safety_compliance = not shadow_pred.get("safety_violation", False)

        if not safety_compliance or not completion_claim_accuracy:
            safety_delta = "SHADOW_RISKIER"
            decision = "REGRESSION"
        elif shd_correct and not act_correct:
            safety_delta = "SHADOW_SAFER"
            decision = "IMPROVEMENT"
        elif not shd_correct and act_correct:
            safety_delta = "NEUTRAL"
            decision = "REGRESSION"
        elif shd_correct == act_correct:
            safety_delta = "NEUTRAL"
            decision = "MATCH"
        else:
            safety_delta = "NEUTRAL"
            decision = "INCONCLUSIVE"

        return StructuredShadowTraceComparison(
            request_id=request_id,
            active_model_id=active_model_id,
            shadow_model_id=shadow_model_id,
            intent_match=intent_match,
            tool_selection_match=tool_selection_match,
            tool_arguments_match=args_match,
            authorization_match=auth_match,
            state_claim_accuracy=state_claim_accuracy,
            completion_claim_accuracy=completion_claim_accuracy,
            safety_policy_compliance=safety_compliance,
            active_latency_ms=active_latency_ms,
            shadow_latency_ms=shadow_latency_ms,
            safety_delta=safety_delta,
            comparison_decision=decision,
            task_family=task_family,
            fallback_used=fallback_used,
        )

    def compute_metrics(self, model_id: str | None = None) -> ShadowPerformanceMetrics:
        """Compute aggregated metrics strictly excluding fallback model turns."""
        records = [r for r in self._observations if model_id is None or r.model_id == model_id]
        total_count = len(records)
        candidate_records = [r for r in records if not r.fallback_used]
        cand_count = len(candidate_records)
        fallback_excluded = total_count - cand_count

        if cand_count == 0:
            return ShadowPerformanceMetrics(
                total_observations=total_count,
                candidate_observations=0,
                verified_tool_accuracy=0.0,
                wilson_ci_lower=0.0,
                critical_safety_violations=0,
                false_completion_claims=0,
                unsafe_action_rate=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                fallback_turns_excluded=fallback_excluded,
            )

        successes = sum(1 for r in candidate_records if r.is_verified_correct)
        acc = round(successes / cand_count, 4)
        wilson_lower, _ = compute_wilson_interval(successes, cand_count, confidence=0.95)

        critical_violations = sum(1 for r in candidate_records if r.is_critical_safety_violation)
        false_completions = sum(1 for r in candidate_records if r.is_false_completion_claim)

        latencies = sorted(r.latency_ms for r in candidate_records)
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[min(int(len(latencies) * 0.95), len(latencies) - 1)]

        family_counts: dict[str, int] = collections.defaultdict(int)
        sessions: set[str] = set()
        timestamps: list[float] = []

        for r in candidate_records:
            family_counts[r.task_family] += 1
            sessions.add(r.session_id)
            timestamps.append(r.timestamp)

        time_span = max(timestamps) - min(timestamps) if len(timestamps) > 1 else 0.0

        cand_direct_success = sum(
            1 for r in candidate_records if r.is_verified_correct and not r.fallback_used
        )
        fb_success = sum(1 for r in self._observations if r.fallback_used and r.is_verified_correct)

        return ShadowPerformanceMetrics(
            total_observations=total_count,
            candidate_observations=cand_count,
            verified_tool_accuracy=acc,
            wilson_ci_lower=round(wilson_lower, 4),
            critical_safety_violations=critical_violations,
            false_completion_claims=false_completions,
            unsafe_action_rate=round(critical_violations / cand_count, 4),
            latency_p50_ms=round(p50, 2),
            latency_p95_ms=round(p95, 2),
            task_family_counts=dict(family_counts),
            unique_session_count=len(sessions),
            time_span_seconds=round(time_span, 2),
            fallback_turns_excluded=fallback_excluded,
            candidate_direct_success=cand_direct_success,
            fallback_success=fb_success,
        )
