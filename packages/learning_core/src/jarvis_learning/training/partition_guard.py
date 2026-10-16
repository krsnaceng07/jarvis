"""jarvis_learning.training.partition_guard — runtime partition isolation and holdout sealing.

Enforces zero leakage between training data and evaluation partitions:
train_sample_ids ∩ (val ∪ test ∪ ood ∪ golden ∪ challenge) == ∅
Guarantees golden holdout remains sealed, immutable, and strictly evaluation-only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from ..datasets.training_contracts import PartitionAccessControl, PartitionAccessMode
from .errors import (
    ChallengePartitionLeakageError,
    GoldenHoldoutViolationError,
    PartitionLeakageError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PartitionSampleManifest:
    """Sample identifiers partitioned by dataset split."""

    train_ids: frozenset[str]
    val_ids: frozenset[str]
    test_ids: frozenset[str]
    ood_ids: frozenset[str]
    golden_ids: frozenset[str]
    challenge_ids: frozenset[str]


class PartitionGuard:
    """Validates runtime partition isolation and prevents leakage."""

    @classmethod
    def verify_isolation(
        cls,
        train_ids: Iterable[str],
        val_ids: Iterable[str] = (),
        test_ids: Iterable[str] = (),
        ood_ids: Iterable[str] = (),
        golden_ids: Iterable[str] = (),
        challenge_ids: Iterable[str] = (),
    ) -> bool:
        """Verify that train_ids has zero intersection with any evaluation partition."""
        train_set = set(train_ids)
        golden_set = set(golden_ids)
        challenge_set = set(challenge_ids)
        val_set = set(val_ids)
        test_set = set(test_ids)
        ood_set = set(ood_ids)

        # 1. Golden holdout check (highest priority: sealed partition)
        golden_overlap = train_set.intersection(golden_set)
        if golden_overlap:
            msg = (
                f"FATAL: Golden holdout partition leakage! {len(golden_overlap)} "
                f"sealed golden samples found in training set (e.g. {sorted(golden_overlap)[:3]})"
            )
            logger.error(msg)
            raise GoldenHoldoutViolationError(msg)

        # 2. Challenge partition check
        challenge_overlap = train_set.intersection(challenge_set)
        if challenge_overlap:
            msg = (
                f"FATAL: Challenge partition leakage! {len(challenge_overlap)} "
                f"challenge samples found in training set (e.g. {sorted(challenge_overlap)[:3]})"
            )
            logger.error(msg)
            raise ChallengePartitionLeakageError(msg)

        # 3. Validation, Test, and OOD holdout check
        eval_union = val_set | test_set | ood_set
        eval_overlap = train_set.intersection(eval_union)
        if eval_overlap:
            msg = (
                f"Partition leakage: {len(eval_overlap)} evaluation samples "
                f"found in training data (e.g. {sorted(eval_overlap)[:3]})"
            )
            logger.error(msg)
            raise PartitionLeakageError(msg)

        logger.debug(
            "Partition isolation verified: train=%d, val=%d, test=%d, ood=%d, golden=%d, challenge=%d",
            len(train_set),
            len(val_set),
            len(test_set),
            len(ood_set),
            len(golden_set),
            len(challenge_set),
        )
        return True

    @classmethod
    def verify_golden_holdout_access(cls, access_mode: PartitionAccessMode) -> None:
        """Assert that golden holdout is accessed strictly for evaluation and never training/tuning."""
        allowed, reason = PartitionAccessControl.check_access("golden_holdout", access_mode)
        if not allowed:
            raise GoldenHoldoutViolationError(
                f"Illegal access mode '{access_mode.value}' for golden_holdout: {reason}"
            )
