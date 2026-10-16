"""jarvis_learning.models.calibration — probability calibration and evaluation.

Transforms raw uncalibrated model probabilities into reliable confidence
estimates using Platt scaling / temperature scaling, and calculates
Expected Calibration Error (ECE) and Brier Score, segmented by task family.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CalibrationMetrics:
    """Metrics assessing calibration quality on a validation set."""

    brier_score: float
    expected_calibration_error: float
    temperature: float
    sample_count: int = 0
    is_valid: bool = True
    task_family: str = "tool_policy"
    dataset_manifest_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ConfidenceCalibrator:
    """Calibrates raw probabilities using temperature / Platt scaling across task families."""

    def __init__(
        self,
        temperature: float = 1.0,
        bias: float = 0.0,
        task_family: str = "tool_policy",
    ) -> None:
        self.temperature = max(0.01, temperature)
        self.bias = bias
        self.task_family = task_family
        self._fitted = False
        self._metrics: CalibrationMetrics | None = None
        self._family_calibrators: dict[str, ConfidenceCalibrator] = {}

    @property
    def is_calibrated(self) -> bool:
        """Return True if calibrator has been fitted with sufficient validation data."""
        return self._fitted and (self._metrics is None or self._metrics.is_valid)

    def calibrate(self, raw_probability: float, task_family: str | None = None) -> float:
        """Apply calibration scaling to a probability value in [0, 1]."""
        family = task_family or self.task_family
        if family in self._family_calibrators:
            return self._family_calibrators[family].calibrate(raw_probability)

        p = max(1e-6, min(1.0 - 1e-6, float(raw_probability)))
        # Convert to logit
        logit = math.log(p / (1.0 - p))
        # Scale logit
        scaled_logit = (logit / self.temperature) + self.bias
        # Sigmoid back to probability
        calibrated = 1.0 / (1.0 + math.exp(-scaled_logit))
        return round(float(calibrated), 4)

    def fit(
        self,
        predicted_probs: list[float],
        true_labels: list[int],
        *,
        num_bins: int = 10,
        task_family: str = "tool_policy",
        dataset_manifest_hash: str = "",
    ) -> CalibrationMetrics:
        """Fit optimal temperature using binary cross-entropy on validation pairs."""
        n_samples = len(predicted_probs)
        if not predicted_probs or n_samples != len(true_labels) or n_samples < 5:
            metrics = CalibrationMetrics(
                brier_score=0.0,
                expected_calibration_error=0.0,
                temperature=1.0,
                sample_count=n_samples,
                is_valid=False,
                task_family=task_family,
                dataset_manifest_hash=dataset_manifest_hash,
                metadata={"reason": "Insufficient samples to calibrate (min 5 required)"},
            )
            self._metrics = metrics
            self._fitted = False
            return metrics

        # Grid search for optimal temperature minimizing NLL
        best_temp = 1.0
        best_nll = float("inf")

        for temp_candidate in [0.2, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0]:
            nll = 0.0
            for prob, label in zip(predicted_probs, true_labels):
                p = max(1e-6, min(1.0 - 1e-6, prob))
                logit = math.log(p / (1.0 - p)) / temp_candidate
                calibrated = 1.0 / (1.0 + math.exp(-logit))
                if label == 1:
                    nll -= math.log(max(1e-6, calibrated))
                else:
                    nll -= math.log(max(1e-6, 1.0 - calibrated))

            if nll < best_nll:
                best_nll = nll
                best_temp = temp_candidate

        self.temperature = best_temp
        self.task_family = task_family
        self._fitted = True

        # Compute post-calibration metrics
        calibrated_probs = [self.calibrate(p) for p in predicted_probs]
        brier = self.compute_brier_score(calibrated_probs, true_labels)
        ece = self.compute_ece(calibrated_probs, true_labels, num_bins=num_bins)

        metrics = CalibrationMetrics(
            brier_score=round(brier, 4),
            expected_calibration_error=round(ece, 4),
            temperature=self.temperature,
            sample_count=n_samples,
            is_valid=True,
            task_family=task_family,
            dataset_manifest_hash=dataset_manifest_hash,
        )
        self._metrics = metrics
        return metrics

    def set_family_calibrator(self, task_family: str, calibrator: ConfidenceCalibrator) -> None:
        """Register a specialized calibrator for a given task family."""
        self._family_calibrators[task_family] = calibrator

    def get_family_calibrator(self, task_family: str) -> ConfidenceCalibrator | None:
        return self._family_calibrators.get(task_family)

    @staticmethod
    def compute_brier_score(probabilities: list[float], labels: list[int]) -> float:
        """Mean squared difference between predicted probability and actual outcome."""
        if not probabilities:
            return 0.0
        total = sum((p - y) ** 2 for p, y in zip(probabilities, labels))
        return total / len(probabilities)

    @staticmethod
    def compute_ece(probabilities: list[float], labels: list[int], num_bins: int = 10) -> float:
        """Expected Calibration Error across partitioned confidence bins."""
        if not probabilities:
            return 0.0

        bin_boundaries = [i / num_bins for i in range(num_bins + 1)]
        total_samples = len(probabilities)
        ece = 0.0

        for i in range(num_bins):
            low = bin_boundaries[i]
            high = bin_boundaries[i + 1]
            bin_indices = [
                idx
                for idx, p in enumerate(probabilities)
                if low <= p < high or (i == num_bins - 1 and p == high)
            ]
            if not bin_indices:
                continue

            bin_size = len(bin_indices)
            avg_confidence = sum(probabilities[idx] for idx in bin_indices) / bin_size
            avg_accuracy = sum(labels[idx] for idx in bin_indices) / bin_size
            ece += (bin_size / total_samples) * abs(avg_accuracy - avg_confidence)

        return ece

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "bias": self.bias,
            "task_family": self.task_family,
            "fitted": self._fitted,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfidenceCalibrator:
        calib = cls(
            temperature=float(data.get("temperature", 1.0)),
            bias=float(data.get("bias", 0.0)),
            task_family=str(data.get("task_family", "tool_policy")),
        )
        calib._fitted = bool(data.get("fitted", False))
        return calib
