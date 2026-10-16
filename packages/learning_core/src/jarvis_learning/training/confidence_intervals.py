"""jarvis_learning.training.confidence_intervals — Wilson score intervals and multi-class decision outcomes.

Computes analytical confidence intervals for binary outcomes and classifies
candidate models into explicit decision categories:
PASS, PASS_WITH_REVIEW, REJECTED_REGRESSION, REJECTED_SAFETY, INSUFFICIENT_EVIDENCE, EVALUATION_FAILED.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass


class EvaluationDecision(enum.StrEnum):
    """Explicit multi-class evaluation verdict."""

    PASS = "PASS"
    PASS_WITH_REVIEW = "PASS_WITH_REVIEW"
    REJECTED_REGRESSION = "REJECTED_REGRESSION"
    REJECTED_SAFETY = "REJECTED_SAFETY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    EVALUATION_FAILED = "EVALUATION_FAILED"


def compute_wilson_interval(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion."""
    if total <= 0:
        return 0.0, 0.0

    # z-score approximation (z=1.96 for 95% confidence)
    z = 1.95996 if confidence >= 0.95 else 1.64485
    p_hat = successes / total

    denominator = 1.0 + (z**2) / total
    center = (p_hat + (z**2) / (2.0 * total)) / denominator
    spread = (
        z * math.sqrt((p_hat * (1.0 - p_hat) / total) + (z**2 / (4.0 * (total**2)))) / denominator
    )

    ci_lower = max(0.0, center - spread)
    ci_upper = min(1.0, center + spread)
    return round(ci_lower, 4), round(ci_upper, 4)


@dataclass(frozen=True, slots=True)
class EvaluatorDecisionEngine:
    """Evaluates metrics with uncertainty bounds and safety triggers."""

    min_samples: int = 10
    min_gain: float = 0.02
    max_regression_tolerance: float = 0.01

    def classify_outcome(
        self,
        candidate_successes: int,
        total_eval_samples: int,
        baseline_accuracy: float,
        critical_safety_violations: int = 0,
        regressed_partitions_count: int = 0,
    ) -> tuple[EvaluationDecision, str]:
        """Classify candidate model into an explicit evaluation decision."""
        # Hard rule: Any critical safety violation triggers immediate REJECTED_SAFETY
        if critical_safety_violations > 0:
            return (
                EvaluationDecision.REJECTED_SAFETY,
                f"Candidate exhibited {critical_safety_violations} critical safety violations",
            )

        if total_eval_samples < self.min_samples:
            return (
                EvaluationDecision.INSUFFICIENT_EVIDENCE,
                f"Sample count ({total_eval_samples}) below required minimum ({self.min_samples})",
            )

        ci_lower, ci_upper = compute_wilson_interval(candidate_successes, total_eval_samples)
        cand_acc = candidate_successes / total_eval_samples
        gain = cand_acc - baseline_accuracy

        # Catastrophic regression on partitions
        if regressed_partitions_count > 0 or gain < -self.max_regression_tolerance:
            return (
                EvaluationDecision.REJECTED_REGRESSION,
                f"Performance regressed by {gain:.1%} (CI: [{ci_lower:.1%}, {ci_upper:.1%}])",
            )

        # Clear improvement exceeding threshold with narrow credible interval
        if gain >= self.min_gain and ci_lower >= baseline_accuracy:
            return (
                EvaluationDecision.PASS,
                f"Significant gain +{gain:.1%} (CI: [{ci_lower:.1%}, {ci_upper:.1%}])",
            )

        if gain >= self.min_gain:
            return (
                EvaluationDecision.PASS_WITH_REVIEW,
                f"Gain +{gain:.1%} exceeds threshold but lower bound ({ci_lower:.1%}) overlaps baseline",
            )

        return (
            EvaluationDecision.REJECTED_REGRESSION,
            f"Gain +{gain:.1%} is below required threshold (+{self.min_gain:.1%})",
        )
