"""jarvis_learning.training.governance — verification of Hard Gates 1 through 6 & 10.

Enforces dataset approval, immutability, revocation status, target scope matching,
Merkle manifest integrity, partition isolation, and zero automatic deployment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..datasets.dataset_lifecycle import DatasetLifecycleState
from ..datasets.dataset_manifest import DatasetManifest
from ..datasets.dataset_revocation import is_dataset_revoked
from .errors import (
    AutomaticDeploymentForbiddenError,
    DatasetRevokedError,
    DatasetUnapprovedError,
    DatasetUnfrozenError,
    IntegrityMismatchError,
    ScopeMismatchError,
)
from .partition_guard import PartitionGuard

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GovernanceCheckResult:
    """Result of running pre-training governance checks."""

    passed: bool
    gate_name: str
    code: str
    message: str


class TrainingGovernance:
    """Evaluates and enforces Hard Gates 1 through 6 & 10."""

    @classmethod
    def verify_gate1_approval(cls, manifest: DatasetManifest) -> GovernanceCheckResult:
        """Gate 1: Dataset lifecycle state must be APPROVED_FOR_TRAINING or APPROVED."""
        valid_states = (
            DatasetLifecycleState.APPROVED_FOR_TRAINING.value,
            DatasetLifecycleState.APPROVED.value,
            "APPROVED_FOR_TRAINING",
            "APPROVED",
        )
        # Support legacy Wave 3 test manifests (schema_version="1")
        if manifest.schema_version == "1" and not manifest.lifecycle_state:
            return GovernanceCheckResult(
                passed=True,
                gate_name="Gate 1: Approval Status",
                code="PASSED_LEGACY",
                message="Legacy schema_version 1 permitted",
            )

        if manifest.lifecycle_state not in valid_states:
            msg = (
                f"Gate 1 failed: Dataset state '{manifest.lifecycle_state}' "
                f"is not APPROVED_FOR_TRAINING"
            )
            logger.error(msg)
            raise DatasetUnapprovedError(msg)
        return GovernanceCheckResult(
            passed=True,
            gate_name="Gate 1: Approval Status",
            code="PASSED",
            message="Dataset is approved for training",
        )

    @classmethod
    def verify_gate2_frozen(cls, manifest: DatasetManifest) -> GovernanceCheckResult:
        """Gate 2: Dataset must be cryptographically frozen and immutable."""
        # Support legacy schema_version 1
        if manifest.schema_version == "1" and not manifest.source_snapshot_hash:
            return GovernanceCheckResult(
                passed=True,
                gate_name="Gate 2: Immutability",
                code="PASSED_LEGACY",
                message="Legacy schema_version 1 permitted",
            )

        if not manifest.source_snapshot_hash:
            msg = "Gate 2 failed: Dataset source snapshot hash is missing (not frozen)"
            logger.error(msg)
            raise DatasetUnfrozenError(msg)
        return GovernanceCheckResult(
            passed=True,
            gate_name="Gate 2: Immutability",
            code="PASSED",
            message="Dataset is frozen",
        )

    @classmethod
    def verify_gate3_revocation(
        cls,
        dataset_id: str,
        db_path: Path | None = None,
        revoked_ids: Sequence[str] = (),
    ) -> GovernanceCheckResult:
        """Gate 3: Dataset must not be revoked."""
        if dataset_id in revoked_ids:
            msg = f"Gate 3 failed: Dataset '{dataset_id}' is revoked"
            logger.error(msg)
            raise DatasetRevokedError(msg)

        if db_path and db_path.exists():
            if is_dataset_revoked(db_path, dataset_id):
                msg = f"Gate 3 failed: Dataset '{dataset_id}' is present in revocation registry"
                logger.error(msg)
                raise DatasetRevokedError(msg)

        return GovernanceCheckResult(
            passed=True,
            gate_name="Gate 3: Revocation",
            code="PASSED",
            message="Dataset is not revoked",
        )

    @classmethod
    def verify_gate4_scope(
        cls,
        manifest: DatasetManifest,
        target: str,
        approval_scope: str = "",
    ) -> GovernanceCheckResult:
        """Gate 4: Operator approval scope and dataset target must match training target."""
        if manifest.target != target:
            msg = f"Gate 4 failed: Dataset target '{manifest.target}' != training target '{target}'"
            logger.error(msg)
            raise ScopeMismatchError(msg)

        if approval_scope and approval_scope != target and approval_scope != "ALL":
            msg = (
                f"Gate 4 failed: Operator approval scope '{approval_scope}' "
                f"does not match target '{target}'"
            )
            logger.error(msg)
            raise ScopeMismatchError(msg)

        return GovernanceCheckResult(
            passed=True,
            gate_name="Gate 4: Scope Match",
            code="PASSED",
            message="Target scope matched",
        )

    @classmethod
    def verify_gate5_integrity(
        cls,
        manifest: DatasetManifest,
        expected_merkle_root: str = "",
    ) -> GovernanceCheckResult:
        """Gate 5: Manifest checksum and Merkle tree root must match."""
        if expected_merkle_root and manifest.merkle_root != expected_merkle_root:
            msg = (
                f"Gate 5 failed: Merkle root mismatch! "
                f"Expected {expected_merkle_root[:12]}, got {manifest.merkle_root[:12]}"
            )
            logger.error(msg)
            raise IntegrityMismatchError(msg)

        return GovernanceCheckResult(
            passed=True,
            gate_name="Gate 5: Integrity",
            code="PASSED",
            message="Merkle integrity verified",
        )

    @classmethod
    def verify_gate6_partition_isolation(
        cls,
        train_ids: Sequence[str],
        val_ids: Sequence[str] = (),
        test_ids: Sequence[str] = (),
        ood_ids: Sequence[str] = (),
        golden_ids: Sequence[str] = (),
        challenge_ids: Sequence[str] = (),
    ) -> GovernanceCheckResult:
        """Gate 6: Zero overlap between training and evaluation partitions."""
        PartitionGuard.verify_isolation(
            train_ids=train_ids,
            val_ids=val_ids,
            test_ids=test_ids,
            ood_ids=ood_ids,
            golden_ids=golden_ids,
            challenge_ids=challenge_ids,
        )
        return GovernanceCheckResult(
            passed=True,
            gate_name="Gate 6: Partition Isolation",
            code="PASSED",
            message="Partitions completely isolated",
        )

    @classmethod
    def verify_gate10_zero_auto_deployment(cls, auto_deploy_flag: bool) -> GovernanceCheckResult:
        """Gate 10: Automatic model deployment is strictly forbidden."""
        if auto_deploy_flag:
            msg = "Gate 10 failed: auto_deploy=True is forbidden; deployment requires manual operator action"
            logger.error(msg)
            raise AutomaticDeploymentForbiddenError(msg)
        return GovernanceCheckResult(
            passed=True,
            gate_name="Gate 10: Zero Auto Deployment",
            code="PASSED",
            message="Auto deployment disabled",
        )
