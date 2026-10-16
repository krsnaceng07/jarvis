"""jarvis_learning.training.quality_gates — dataset size minimums and imbalance action policies.

Enforces sample count minimums, class diversity, and imbalance/collapse resolution
before allowing training to consume a dataset.
"""

from __future__ import annotations

import enum
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Sequence

from .errors import TrainingError

logger = logging.getLogger(__name__)


class ImbalanceAction(enum.StrEnum):
    """Action taken when severe class imbalance or collapse is detected."""

    REJECT = "REJECT"
    REQUIRE_OPERATOR_REVIEW = "REQUIRE_OPERATOR_REVIEW"
    REWEIGHT = "REWEIGHT"
    CONTINUE_WITH_WARNING = "CONTINUE_WITH_WARNING"


class QualityGateError(TrainingError):
    """Raised when a dataset fails minimum quality or statistical size requirements."""

    def __init__(self, message: str, code: str = "QUALITY_GATE_FAILED") -> None:
        super().__init__(message, code=code)


@dataclass(frozen=True, slots=True)
class DatasetQualityPolicy:
    """Configurable thresholds and response policies for dataset quality."""

    min_train_samples: int = 10
    min_validation_samples: int = 2
    min_class_count: int = 2
    min_unique_groups: int = 2
    min_preference_pairs: int = 5
    max_majority_class_ratio: float = 0.90
    imbalance_action: ImbalanceAction = ImbalanceAction.REQUIRE_OPERATOR_REVIEW


@dataclass(frozen=True, slots=True)
class QualityCheckReport:
    """Diagnostic outcome of dataset quality validation."""

    passed: bool
    train_sample_count: int
    val_sample_count: int
    class_count: int
    unique_group_count: int
    majority_class_ratio: float
    detected_anomalies: tuple[str, ...]
    action_taken: ImbalanceAction


class DatasetQualityGate:
    """Validates dataset size minimums and imbalance thresholds."""

    @classmethod
    def check_quality(
        cls,
        train_samples: Sequence[dict[str, Any]],
        val_samples: Sequence[dict[str, Any]],
        policy: DatasetQualityPolicy | None = None,
        is_preference_task: bool = False,
    ) -> QualityCheckReport:
        """Run complete statistical quality audit on input samples."""
        pol = policy or DatasetQualityPolicy()
        anomalies: list[str] = []

        train_count = len(train_samples)
        val_count = len(val_samples)

        # 1. Check minimum sample counts
        if train_count < pol.min_train_samples:
            anomalies.append(
                f"Train count ({train_count}) below minimum threshold ({pol.min_train_samples})"
            )

        if val_count < pol.min_validation_samples:
            anomalies.append(
                f"Validation count ({val_count}) below minimum threshold ({pol.min_validation_samples})"
            )

        # 2. Extract classes and groups
        labels = [s.get("label", {}).get("tool", "") for s in train_samples if s.get("label")]
        groups = [s.get("group_id", s.get("session_id", "")) for s in train_samples]
        unique_groups = len(set(g for g in groups if g))

        class_counts = Counter(lbl for lbl in labels if lbl)
        class_count = len(class_counts)

        if class_count < pol.min_class_count:
            anomalies.append(
                f"Unique classes ({class_count}) below minimum required ({pol.min_class_count})"
            )

        if unique_groups > 0 and unique_groups < pol.min_unique_groups:
            anomalies.append(
                f"Unique groups ({unique_groups}) below minimum required ({pol.min_unique_groups})"
            )

        # 3. Check majority class ratio
        majority_ratio = 0.0
        if train_count > 0 and class_counts:
            most_common_count = class_counts.most_common(1)[0][1]
            majority_ratio = round(most_common_count / train_count, 4)
            if majority_ratio > pol.max_majority_class_ratio:
                anomalies.append(
                    f"SEVERE_CLASS_IMBALANCE: majority class accounts for {majority_ratio:.1%} "
                    f"(ceiling={pol.max_majority_class_ratio:.1%})"
                )

        has_critical_failure = (
            train_count < pol.min_train_samples
            or val_count < pol.min_validation_samples
            or class_count < pol.min_class_count
        )

        action = pol.imbalance_action
        if has_critical_failure:
            action = ImbalanceAction.REJECT

        passed = not has_critical_failure and action != ImbalanceAction.REJECT

        if not passed:
            msg = f"Dataset quality gate rejected: {'; '.join(anomalies)}"
            logger.error(msg)
            raise QualityGateError(msg, code="QUALITY_GATE_FAILED")

        return QualityCheckReport(
            passed=passed,
            train_sample_count=train_count,
            val_sample_count=val_count,
            class_count=class_count,
            unique_group_count=unique_groups,
            majority_class_ratio=majority_ratio,
            detected_anomalies=tuple(anomalies),
            action_taken=action,
        )
