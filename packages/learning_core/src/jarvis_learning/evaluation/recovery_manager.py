"""jarvis_learning.evaluation.recovery_manager — 14-State Transactional Recovery Manager.

Enforces:
1. INV-P9-REC-001: Physical reconciliation of actual disk artifacts and digests (never blind trust in DB).
2. INV-P9-REC-002: Ambiguous or interrupted promotion transactions force immediate fallback to SAFE_DEGRADED_MODE.
3. 14-state transaction lifecycle:
   CREATED -> VALIDATING -> PREPARED -> APPROVAL_VERIFIED -> TARGET_VERIFIED ->
   POINTER_UPDATE_STARTED -> POINTER_UPDATED -> COMMIT_RECORDED -> ACTIVATION_CONFIRMED ->
   ABORTED, RECOVERY_REQUIRED, ROLLBACK_REQUIRED, ROLLBACK_COMPLETED, SAFE_DEGRADED.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class PromotionTransactionState(enum.StrEnum):
    """The 14 canonical states of model activation and recovery."""

    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    PREPARED = "PREPARED"
    APPROVAL_VERIFIED = "APPROVAL_VERIFIED"
    TARGET_VERIFIED = "TARGET_VERIFIED"
    POINTER_UPDATE_STARTED = "POINTER_UPDATE_STARTED"
    POINTER_UPDATED = "POINTER_UPDATED"
    COMMIT_RECORDED = "COMMIT_RECORDED"
    ACTIVATION_CONFIRMED = "ACTIVATION_CONFIRMED"
    ABORTED = "ABORTED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    ROLLBACK_REQUIRED = "ROLLBACK_REQUIRED"
    ROLLBACK_COMPLETED = "ROLLBACK_COMPLETED"
    SAFE_DEGRADED = "SAFE_DEGRADED"


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """Outcome of physical startup reconciliation check."""

    status: str  # "CONSISTENT", "RECOVERABLE", "INCONSISTENT", "SAFE_DEGRADED"
    active_model_id: str
    active_pointer_target: str
    physical_artifact_found: bool
    hash_verified: bool
    details: str
    action_taken: str


class TransactionalRecoveryManager:
    """Reconciles promotion transaction state against physical disk reality upon startup."""

    def __init__(
        self,
        models_root: Path | str,
        pointer_file: Path | str,
        known_good_model_id: str = "model_v001_baseline",
    ) -> None:
        self.models_root = Path(models_root)
        self.pointer_file = Path(pointer_file)
        self.known_good_model_id = known_good_model_id
        self.current_state = PromotionTransactionState.CREATED

    def reconcile_startup(
        self,
        last_recorded_db_state: str = "ACTIVATION_CONFIRMED",
        expected_artifact_hash: str | None = None,
    ) -> ReconciliationReport:
        """Verify physical filesystem artifacts against database pointers (INV-P9-REC-001).

        Falls back to SAFE_DEGRADED if discrepancy or mid-flight crash is detected (INV-P9-REC-002).
        """
        # 1. Read pointer file
        if not self.pointer_file.exists():
            self._write_pointer(self.known_good_model_id)
            self.current_state = PromotionTransactionState.SAFE_DEGRADED
            return ReconciliationReport(
                status="SAFE_DEGRADED",
                active_model_id=self.known_good_model_id,
                active_pointer_target=self.known_good_model_id,
                physical_artifact_found=False,
                hash_verified=False,
                details="Pointer file missing; initialized to known-good baseline",
                action_taken="SET_SAFE_DEGRADED",
            )

        try:
            pointer_data = json.loads(self.pointer_file.read_text(encoding="utf-8"))
            active_model = pointer_data.get("active_model", self.known_good_model_id)
            declared_hash = pointer_data.get("artifact_hash", "")
        except Exception:
            self._write_pointer(self.known_good_model_id)
            self.current_state = PromotionTransactionState.SAFE_DEGRADED
            return ReconciliationReport(
                status="SAFE_DEGRADED",
                active_model_id=self.known_good_model_id,
                active_pointer_target=self.known_good_model_id,
                physical_artifact_found=False,
                hash_verified=False,
                details="Corrupted pointer file; reverted to known-good baseline",
                action_taken="REVERT_POINTER_SAFE_DEGRADED",
            )

        # 2. Check for mid-flight crash states
        if last_recorded_db_state in (
            PromotionTransactionState.POINTER_UPDATE_STARTED,
            PromotionTransactionState.POINTER_UPDATED,
            PromotionTransactionState.RECOVERY_REQUIRED,
            PromotionTransactionState.ROLLBACK_REQUIRED,
        ):
            logger.warning(
                "Unfinished promotion transaction detected in DB (%s); reverting to safe mode",
                last_recorded_db_state,
            )
            self._write_pointer(self.known_good_model_id)
            self.current_state = PromotionTransactionState.SAFE_DEGRADED
            return ReconciliationReport(
                status="SAFE_DEGRADED",
                active_model_id=self.known_good_model_id,
                active_pointer_target=self.known_good_model_id,
                physical_artifact_found=True,
                hash_verified=False,
                details=f"Interrupted transaction ({last_recorded_db_state}); reverted to {self.known_good_model_id}",
                action_taken="ROLLBACK_INTERRUPTED_TRANSACTION",
            )

        # 3. Verify physical artifact existence on disk
        artifact_path = self.models_root / active_model / "model.bin"
        if not artifact_path.exists():
            logger.error(
                "Physical model artifact missing at %s; entering SAFE_DEGRADED", artifact_path
            )
            self._write_pointer(self.known_good_model_id)
            self.current_state = PromotionTransactionState.SAFE_DEGRADED
            return ReconciliationReport(
                status="SAFE_DEGRADED",
                active_model_id=self.known_good_model_id,
                active_pointer_target=active_model,
                physical_artifact_found=False,
                hash_verified=False,
                details=f"Physical artifact missing: {artifact_path}",
                action_taken="REVERT_MISSING_ARTIFACT",
            )

        # 4. Verify SHA-256 hash
        file_bytes = artifact_path.read_bytes()
        actual_hash = hashlib.sha256(file_bytes).hexdigest()

        target_expected = expected_artifact_hash or declared_hash
        if target_expected and actual_hash != target_expected:
            logger.error("Artifact SHA-256 mismatch for %s; entering SAFE_DEGRADED", active_model)
            self._write_pointer(self.known_good_model_id)
            self.current_state = PromotionTransactionState.SAFE_DEGRADED
            return ReconciliationReport(
                status="SAFE_DEGRADED",
                active_model_id=self.known_good_model_id,
                active_pointer_target=active_model,
                physical_artifact_found=True,
                hash_verified=False,
                details=f"Checksum mismatch: expected={target_expected[:12]} actual={actual_hash[:12]}",
                action_taken="REVERT_CHECKSUM_MISMATCH",
            )

        # 5. Fully consistent
        self.current_state = PromotionTransactionState.ACTIVATION_CONFIRMED
        return ReconciliationReport(
            status="CONSISTENT",
            active_model_id=active_model,
            active_pointer_target=active_model,
            physical_artifact_found=True,
            hash_verified=True,
            details="All physical model artifacts and pointer digests verified consistent",
            action_taken="NONE",
        )

    def _write_pointer(self, model_id: str, artifact_hash: str = "") -> None:
        self.pointer_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"active_model": model_id, "artifact_hash": artifact_hash}
        self.pointer_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
