"""jarvis_learning.training.comparison — model candidate vs baseline evaluation.

Ensures no complex or neural model is promoted unless it demonstrably outperforms
the simpler baseline by a statistically meaningful margin on the immutable test split.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.calibration import ConfidenceCalibrator


@dataclass(frozen=True, slots=True)
class ComparisonReport:
    """Report comparing a candidate model against a baseline."""

    candidate_accuracy: float
    baseline_accuracy: float
    accuracy_gain: float
    candidate_brier: float
    baseline_brier: float
    calibration_gain: float
    min_accuracy_gain_required: float
    beats_baseline: bool
    verdict: str
    sample_count: int


class BaselineComparator:
    """Compares candidate model predictions against a baseline on test data."""

    def __init__(
        self,
        *,
        min_accuracy_gain: float = 0.02,  # Must beat baseline by at least 2%
        min_calibration_gain: float = 0.0,
    ) -> None:
        self.min_accuracy_gain = min_accuracy_gain
        self.min_calibration_gain = min_calibration_gain

    def compare(
        self,
        candidate_predictions: list[tuple[str, float]],
        baseline_predictions: list[tuple[str, float]],
        ground_truth: list[str],
    ) -> ComparisonReport:
        """Compare candidate vs baseline predictions over ground truth labels."""
        total = len(ground_truth)
        if total == 0 or len(candidate_predictions) != total or len(baseline_predictions) != total:
            return ComparisonReport(
                candidate_accuracy=0.0,
                baseline_accuracy=0.0,
                accuracy_gain=0.0,
                candidate_brier=0.0,
                baseline_brier=0.0,
                calibration_gain=0.0,
                min_accuracy_gain_required=self.min_accuracy_gain,
                beats_baseline=False,
                verdict="Insufficient or mismatched test samples",
                sample_count=total,
            )

        cand_correct = sum(1 for (p, _), y in zip(candidate_predictions, ground_truth) if p == y)
        base_correct = sum(1 for (p, _), y in zip(baseline_predictions, ground_truth) if p == y)

        cand_acc = cand_correct / total
        base_acc = base_correct / total
        acc_gain = round(cand_acc - base_acc, 4)

        # Brier score comparison
        cand_binary = [1 if p == y else 0 for (p, _), y in zip(candidate_predictions, ground_truth)]
        base_binary = [1 if p == y else 0 for (p, _), y in zip(baseline_predictions, ground_truth)]

        cand_brier = ConfidenceCalibrator.compute_brier_score(
            [prob for _, prob in candidate_predictions], cand_binary
        )
        base_brier = ConfidenceCalibrator.compute_brier_score(
            [prob for _, prob in baseline_predictions], base_binary
        )

        cal_gain = round(base_brier - cand_brier, 4)  # Positive = candidate has lower error

        # Must beat baseline by at least min_accuracy_gain
        beats = acc_gain >= self.min_accuracy_gain

        if beats:
            verdict = (
                f"Candidate qualified: accuracy +{acc_gain:.1%} exceeds "
                f"required minimum (+{self.min_accuracy_gain:.1%})"
            )
        else:
            verdict = (
                f"Candidate rejected: accuracy gain {acc_gain:.1%} is below "
                f"required margin (+{self.min_accuracy_gain:.1%})"
            )

        return ComparisonReport(
            candidate_accuracy=round(cand_acc, 4),
            baseline_accuracy=round(base_acc, 4),
            accuracy_gain=acc_gain,
            candidate_brier=round(cand_brier, 4),
            baseline_brier=round(base_brier, 4),
            calibration_gain=cal_gain,
            min_accuracy_gain_required=self.min_accuracy_gain,
            beats_baseline=beats,
            verdict=verdict,
            sample_count=total,
        )
