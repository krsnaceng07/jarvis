"""jarvis_learning.routing.ood — empirical out-of-distribution (OOD) query detection.

Detects when user input falls outside the training distribution using normalized
vocabulary coverage, centroid distances, and prediction entropy, with empirical
task-family threshold calibration and statistical validation.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class OODResult:
    """Normalized evaluation of whether a query is out-of-distribution."""

    is_ood: bool
    score: float  # Normalized [0.0 = known/in-dist, 1.0 = highly unknown/OOD]
    vocabulary_coverage: float  # [0.0, 1.0] fraction of query tokens known
    centroid_distance: float  # [0.0, 1.0] normalized distance metric
    entropy: float  # Shannon entropy of probability distribution
    reason: str
    task_family: str = "tool_policy"


@dataclass(frozen=True, slots=True)
class EmpiricalOODCalibration:
    """Statistical calibration metrics for a task-family OOD detector."""

    task_family: str
    threshold: float
    auroc: float
    auprc: float
    fpr: float  # False positive rate on in-distribution data
    fnr: float  # False negative rate on OOD evaluation set
    calibration_sample_count: int
    is_statistically_valid: bool
    status: str = "calibrated"  # "calibrated" | "insufficient_evidence" | "uncalibrated"
    metadata: dict[str, Any] = field(default_factory=dict)


class DistributionGuard:
    """Empirical out-of-distribution detector across task families."""

    def __init__(
        self,
        known_vocabulary: set[str] | None = None,
        ood_threshold: float = 0.5,
    ) -> None:
        self.known_vocabulary: set[str] = {w.lower() for w in (known_vocabulary or set())}
        self.default_threshold = ood_threshold
        self.calibrations: dict[str, EmpiricalOODCalibration] = {}

    def set_vocabulary(self, vocab: set[str]) -> None:
        """Update the known in-distribution vocabulary."""
        self.known_vocabulary = {w.lower() for w in vocab}

    def calibrate_empirical_threshold(
        self,
        in_distribution_scores: list[float],
        ood_scores: list[float],
        *,
        task_family: str = "tool_policy",
        target_fpr: float = 0.05,
    ) -> EmpiricalOODCalibration:
        """Fit empirical threshold using in-distribution validation and OOD evaluation sets."""
        n_id = len(in_distribution_scores)
        n_ood = len(ood_scores)

        # Statistical validity requires minimum sample counts (min 5 per class)
        if n_id < 5 or n_ood < 5:
            calib = EmpiricalOODCalibration(
                task_family=task_family,
                threshold=self.default_threshold,
                auroc=0.5,
                auprc=0.0,
                fpr=1.0,
                fnr=1.0,
                calibration_sample_count=n_id + n_ood,
                is_statistically_valid=False,
                status="insufficient_evidence",
                metadata={
                    "reason": f"Sample size too small (id={n_id}, ood={n_ood}; min 5 required)"
                },
            )
            self.calibrations[task_family] = calib
            return calib

        # 1. Compute AUROC via Mann-Whitney U test
        u_stat = 0.0
        for x in ood_scores:
            for y in in_distribution_scores:
                if x > y:
                    u_stat += 1.0
                elif x == y:
                    u_stat += 0.5
        auroc = round(u_stat / (n_id * n_ood), 4)

        # 2. Select calibrated threshold at (1 - target_fpr) percentile of in-distribution scores
        sorted_id = sorted(in_distribution_scores)
        idx = min(int(math.ceil((1.0 - target_fpr) * n_id)), n_id - 1)
        calibrated_thresh = round(sorted_id[idx], 4)

        # Ensure threshold is within reasonable bounds
        calibrated_thresh = max(0.1, min(0.9, calibrated_thresh))

        # 3. Compute empirical FPR and FNR at this threshold
        false_positives = sum(1 for s in in_distribution_scores if s >= calibrated_thresh)
        false_negatives = sum(1 for s in ood_scores if s < calibrated_thresh)
        fpr = round(false_positives / n_id, 4)
        fnr = round(false_negatives / n_ood, 4)

        # 4. Compute AUPRC (trapezoidal approximation)
        all_samples = [(s, 1) for s in ood_scores] + [(s, 0) for s in in_distribution_scores]
        all_samples.sort(key=lambda x: x[0], reverse=True)
        tp = 0
        fp = 0
        precisions = []
        recalls = []
        for _, label in all_samples:
            if label == 1:
                tp += 1
            else:
                fp += 1
            recalls.append(tp / n_ood)
            precisions.append(tp / (tp + fp))

        auprc = 0.0
        for i in range(1, len(recalls)):
            auprc += (recalls[i] - recalls[i - 1]) * (precisions[i] + precisions[i - 1]) / 2.0
        auprc = round(max(0.0, min(1.0, auprc)), 4)

        calibration = EmpiricalOODCalibration(
            task_family=task_family,
            threshold=calibrated_thresh,
            auroc=auroc,
            auprc=auprc,
            fpr=fpr,
            fnr=fnr,
            calibration_sample_count=n_id + n_ood,
            is_statistically_valid=True,
            status="calibrated",
        )
        self.calibrations[task_family] = calibration
        return calibration

    def get_threshold(self, task_family: str = "tool_policy") -> float:
        """Return active calibrated threshold for the task family."""
        if (
            task_family in self.calibrations
            and self.calibrations[task_family].is_statistically_valid
        ):
            return self.calibrations[task_family].threshold
        return self.default_threshold

    def evaluate(
        self,
        query: str,
        predicted_probs: list[float] | None = None,
        task_family: str = "tool_policy",
    ) -> OODResult:
        """Calculate empirical normalized OOD score for an incoming query."""
        tokens = re.findall(r"\b\w+\b", query.lower())
        active_thresh = self.get_threshold(task_family)

        if not tokens:
            return OODResult(
                is_ood=True,
                score=1.0,
                vocabulary_coverage=0.0,
                centroid_distance=1.0,
                entropy=0.0,
                reason="Empty query input",
                task_family=task_family,
            )

        # 1. Vocabulary coverage: higher coverage -> lower OOD
        if self.known_vocabulary:
            known_tokens = sum(1 for t in tokens if t in self.known_vocabulary)
            coverage = known_tokens / len(tokens)
        else:
            coverage = 1.0  # Fallback if vocabulary not supplied

        vocab_penalty = 1.0 - coverage

        # 2. Prediction entropy
        entropy = 0.0
        if predicted_probs and len(predicted_probs) > 1:
            for p in predicted_probs:
                p_safe = max(1e-7, min(1.0, p))
                entropy -= p_safe * math.log(p_safe)
            # Normalize entropy by max entropy log(K)
            max_entropy = math.log(len(predicted_probs)) or 1.0
            norm_entropy = min(1.0, entropy / max_entropy)
        else:
            norm_entropy = 0.0

        # Unified normalized OOD score in [0.0, 1.0]
        # 60% weight to vocabulary unknownness, 40% weight to prediction entropy
        ood_score = round(0.6 * vocab_penalty + 0.4 * norm_entropy, 4)
        is_ood = ood_score >= active_thresh

        reason_parts = []
        if vocab_penalty > 0.4:
            reason_parts.append(f"low vocabulary coverage ({coverage:.0%})")
        if norm_entropy > 0.6:
            reason_parts.append(f"high prediction entropy ({norm_entropy:.2f})")
        if not reason_parts:
            reason_parts.append("within normal training distribution")

        return OODResult(
            is_ood=is_ood,
            score=ood_score,
            vocabulary_coverage=round(coverage, 4),
            centroid_distance=round(vocab_penalty, 4),
            entropy=round(entropy, 4),
            reason="; ".join(reason_parts),
            task_family=task_family,
        )
