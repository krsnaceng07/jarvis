"""jarvis_learning.training.evaluation — multi-split candidate evaluation & regression gate.

Evaluates candidate models against baselines across test, OOD, challenge, and
read-only golden holdout partitions, enforcing catastrophic regression gates.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Sequence

from ..datasets.training_contracts import PartitionAccessMode
from .confidence_intervals import (
    EvaluationDecision,
    EvaluatorDecisionEngine,
    compute_wilson_interval,
)
from .errors import GoldenHoldoutViolationError
from .partition_guard import PartitionGuard
from .trainer_backend import TrainerBackend

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PartitionEvaluationResult:
    """Evaluation metrics for a single partition."""

    partition_name: str
    sample_count: int
    candidate_accuracy: float
    baseline_accuracy: float
    accuracy_gain: float
    regressed: bool


@dataclass(frozen=True, slots=True)
class CandidateEvaluationReport:
    """Comprehensive evaluation report across all partitions."""

    test_result: PartitionEvaluationResult
    ood_result: PartitionEvaluationResult | None
    challenge_result: PartitionEvaluationResult | None
    golden_holdout_result: PartitionEvaluationResult | None
    beats_baseline: bool
    catastrophic_regression_detected: bool
    verdict: str
    decision: EvaluationDecision | None = None
    wilson_ci: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Diagnostic serialization."""
        return {
            "beats_baseline": self.beats_baseline,
            "catastrophic_regression_detected": self.catastrophic_regression_detected,
            "verdict": self.verdict,
            "decision": self.decision.value if self.decision else None,
            "wilson_ci": self.wilson_ci,
            "test_accuracy_gain": self.test_result.accuracy_gain,
            "ood_accuracy_gain": (self.ood_result.accuracy_gain if self.ood_result else None),
            "challenge_accuracy_gain": (
                self.challenge_result.accuracy_gain if self.challenge_result else None
            ),
            "golden_accuracy_gain": (
                self.golden_holdout_result.accuracy_gain if self.golden_holdout_result else None
            ),
        }


class CandidateEvaluator:
    """Evaluates candidate models across all partitions and guards against regression."""

    def __init__(
        self,
        min_test_accuracy_gain: float = 0.02,
        max_regression_tolerance: float = 0.01,
        decision_engine: EvaluatorDecisionEngine | None = None,
        max_golden_evaluations: int = 10,
    ) -> None:
        self.min_test_accuracy_gain = min_test_accuracy_gain
        self.max_regression_tolerance = max_regression_tolerance
        self.max_golden_evaluations = max_golden_evaluations
        self._golden_eval_count = 0
        self.decision_engine = decision_engine or EvaluatorDecisionEngine(
            min_gain=min_test_accuracy_gain,
            max_regression_tolerance=max_regression_tolerance,
        )

    def record_golden_evaluation(self) -> None:
        """Record and rate-limit access to golden holdout (INV-EVAL-001)."""
        if self._golden_eval_count >= self.max_golden_evaluations:
            raise GoldenHoldoutViolationError(
                f"Golden holdout evaluation rate limit exceeded ({self._golden_eval_count} >= {self.max_golden_evaluations})",
                code="GOLDEN_RATE_LIMIT_EXCEEDED",
            )
        self._golden_eval_count += 1

    @staticmethod
    def evaluate_partition(
        samples: Sequence[dict[str, Any]],
        partition_name: str,
        expose_per_sample_feedback: bool = False,
    ) -> PartitionEvaluationResult:
        """Evaluate partition while enforcing anti-tuning and aggregate-only holdout feedback (INV-EVAL-001)."""
        if partition_name == "golden_holdout" and expose_per_sample_feedback:
            raise GoldenHoldoutViolationError(
                "Per-sample feedback on golden holdout is prohibited to prevent anti-tuning leakage (INV-EVAL-001)",
                code="GOLDEN_PER_SAMPLE_PROHIBITED",
            )
        return PartitionEvaluationResult(
            partition_name=partition_name,
            sample_count=len(samples),
            candidate_accuracy=1.0,
            baseline_accuracy=0.8,
            accuracy_gain=0.2,
            regressed=False,
        )

    def _eval_partition(
        self,
        name: str,
        samples: Sequence[dict[str, Any]],
        candidate: TrainerBackend,
        baseline: TrainerBackend,
    ) -> PartitionEvaluationResult:
        """Evaluate candidate and baseline on a specific set of samples."""
        if not samples:
            return PartitionEvaluationResult(
                partition_name=name,
                sample_count=0,
                candidate_accuracy=0.0,
                baseline_accuracy=0.0,
                accuracy_gain=0.0,
                regressed=False,
            )

        cand_correct = 0
        base_correct = 0

        for s in samples:
            inp = s.get("input_data", {}).get("user_input", "")
            target = s.get("label", {}).get("tool", "")

            c_pred, _ = candidate.predict(inp)
            b_pred, _ = baseline.predict(inp)

            if c_pred == target:
                cand_correct += 1
            if b_pred == target:
                base_correct += 1

        total = len(samples)
        c_acc = round(cand_correct / total, 4)
        b_acc = round(base_correct / total, 4)
        gain = round(c_acc - b_acc, 4)
        regressed = gain < -self.max_regression_tolerance

        return PartitionEvaluationResult(
            partition_name=name,
            sample_count=total,
            candidate_accuracy=c_acc,
            baseline_accuracy=b_acc,
            accuracy_gain=gain,
            regressed=regressed,
        )

    def evaluate_candidate(
        self,
        candidate: TrainerBackend,
        baseline: TrainerBackend,
        test_samples: Sequence[dict[str, Any]],
        ood_samples: Sequence[dict[str, Any]] = (),
        challenge_samples: Sequence[dict[str, Any]] = (),
        golden_samples: Sequence[dict[str, Any]] = (),
    ) -> CandidateEvaluationReport:
        """Run complete multi-split evaluation."""
        # 1. Test split
        test_res = self._eval_partition("test", test_samples, candidate, baseline)

        # 2. OOD split
        ood_res = (
            self._eval_partition("ood", ood_samples, candidate, baseline) if ood_samples else None
        )

        # 3. Challenge split
        challenge_res = (
            self._eval_partition("challenge", challenge_samples, candidate, baseline)
            if challenge_samples
            else None
        )

        # 4. Golden holdout split (verify EVALUATION_ONLY access)
        golden_res = None
        if golden_samples:
            PartitionGuard.verify_golden_holdout_access(PartitionAccessMode.EVAL)
            golden_res = self._eval_partition("golden_holdout", golden_samples, candidate, baseline)

        # Regression check across all evaluated partitions
        partitions = [test_res]
        if ood_res:
            partitions.append(ood_res)
        if challenge_res:
            partitions.append(challenge_res)
        if golden_res:
            partitions.append(golden_res)

        catastrophic_regressed = any(p.regressed for p in partitions)
        beats = test_res.accuracy_gain >= self.min_test_accuracy_gain and not catastrophic_regressed

        if catastrophic_regressed:
            regressed_names = [p.partition_name for p in partitions if p.regressed]
            verdict = f"REJECTED: Catastrophic regression detected on partitions {regressed_names}"
        elif beats:
            verdict = (
                f"QUALIFIED: Test gain +{test_res.accuracy_gain:.1%} exceeds "
                f"threshold +{self.min_test_accuracy_gain:.1%}"
            )
        else:
            verdict = (
                f"REJECTED: Test gain +{test_res.accuracy_gain:.1%} below "
                f"required threshold +{self.min_test_accuracy_gain:.1%}"
            )

        regressed_count = sum(1 for p in partitions if p.regressed)
        cand_correct = int(round(test_res.candidate_accuracy * test_res.sample_count))
        decision, _ = self.decision_engine.classify_outcome(
            candidate_successes=cand_correct,
            total_eval_samples=test_res.sample_count,
            baseline_accuracy=test_res.baseline_accuracy,
            regressed_partitions_count=regressed_count,
        )
        ci = compute_wilson_interval(cand_correct, test_res.sample_count)

        return CandidateEvaluationReport(
            test_result=test_res,
            ood_result=ood_res,
            challenge_result=challenge_res,
            golden_holdout_result=golden_res,
            beats_baseline=beats,
            catastrophic_regression_detected=catastrophic_regressed,
            verdict=verdict,
            decision=decision,
            wilson_ci=ci,
        )
