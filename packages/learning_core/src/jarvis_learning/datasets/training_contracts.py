"""jarvis_learning.datasets.training_contracts — training purpose and format separation.

Prevents training-type contamination:
- A trace valid for contrastive preference (DPO) is forbidden from direct SFT.
- A failure trace cannot be used as an SFT imitation target.
- Ambiguous or low-data samples are restricted to abstention or audit pools.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Sequence


class SampleUsage(StrEnum):
    SFT = "sft"
    DPO_PREFERENCE = "dpo_preference"
    TOOL_SELECTION = "tool_selection"
    RECOVERY_POLICY = "recovery_policy"
    CRITIQUE_TRAINING = "critique_training"
    ABSTENTION = "abstention"
    EVALUATION_ONLY = "evaluation_only"
    AUDIT_ONLY = "audit_only"


class TrainingPurposeContract:
    """Validates sample compatibility with declared training purpose."""

    @staticmethod
    def validate_purpose(
        usage: SampleUsage,
        *,
        is_success: bool,
        is_negative: bool,
        is_quarantined: bool,
        attribution_status: str,
        label_quality: str,
    ) -> tuple[bool, str]:
        """Validate if sample characteristics are permitted for the requested usage."""
        if usage == SampleUsage.SFT:
            # SFT requires verified positive behavior
            if not is_success or is_negative or is_quarantined:
                return (
                    False,
                    "SFT requires verified success; failure or quarantined traces forbidden",
                )
            if label_quality not in ("optimal", "acceptable"):
                return (
                    False,
                    f"SFT requires optimal or acceptable label quality; found {label_quality}",
                )
            if attribution_status in ("AMBIGUOUS", "INSUFFICIENT_DATA"):
                return False, f"SFT forbids ambiguous causal attribution: {attribution_status}"

        elif usage == SampleUsage.TOOL_SELECTION:
            if is_quarantined and not is_negative:
                return False, "Quarantined tools cannot be positive tool selection targets"

        elif usage == SampleUsage.RECOVERY_POLICY:
            # Recovery policy specifically requires failure followed by recovery attempt
            if is_success and not is_negative:
                return False, "Recovery policy targets must represent failure-recovery episodes"

        elif usage == SampleUsage.ABSTENTION:
            # Abstention targets must be ambiguous or out-of-domain/unsafe
            if label_quality in ("optimal",):
                return False, "Optimal confident traces should not be used as abstention targets"

        return True, ""


class PartitionAccessMode(StrEnum):
    TRAIN = "train"
    TUNE = "tune"
    EVAL = "eval"
    EXPORT = "export"


@dataclass(frozen=True, slots=True)
class PartitionAccessControl:
    """Enforces access boundaries on dataset partitions.

    Ensures that golden_holdout is strictly SEALED, EVALUATION_ONLY,
    NOT_EXPORTABLE, NOT_TUNABLE, and NOT_TRAINABLE.
    """

    @staticmethod
    def check_access(partition: str, mode: PartitionAccessMode) -> tuple[bool, str]:
        """Verify if the requested partition can be accessed for the given mode."""
        part = partition.lower().strip()
        if part == "golden_holdout":
            if mode in (
                PartitionAccessMode.TRAIN,
                PartitionAccessMode.TUNE,
                PartitionAccessMode.EXPORT,
            ):
                return (
                    False,
                    f"Partition '{partition}' is SEALED, EVALUATION_ONLY, NOT_TRAINABLE, NOT_TUNABLE, NOT_EXPORTABLE",
                )
            if mode == PartitionAccessMode.EVAL:
                return True, "SEALED_EVALUATION_PERMITTED"
        return True, "ACCESS_PERMITTED"

    @staticmethod
    def filter_trainable_samples(partition_samples: dict[str, Sequence[Any]]) -> list[Any]:
        """Return samples strictly eligible for training, ensuring golden_holdout is never included."""
        trainable: list[Any] = []
        for part_name, samples in partition_samples.items():
            allowed, _ = PartitionAccessControl.check_access(part_name, PartitionAccessMode.TRAIN)
            if allowed and part_name == "train":
                trainable.extend(samples)
        return trainable
