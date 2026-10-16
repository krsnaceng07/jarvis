"""Master RebootPersistenceHarness orchestrator for Track 2.2.

Coordinates:
1. Pre-reboot preparation & arming (workload, SQLite WAL, manifest sealing, scheduled task)
2. Post-reboot verification (boot advance causality, forensic quarantine, pointer rollback, PRAGMAs)
3. Multi-dimensional qualification (truthful evidence classification without simulation inflation)
4. In-suite durability auditing (for continuous regression and CI proof)
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any

from jarvis_learning.invariants_p10 import EvidenceLevel
from jarvis_learning.persistence.artifact_manifest import (
    PreRebootManifest,
    PreRebootManifestBuilder,
)
from jarvis_learning.persistence.artifact_reconciler import ArtifactReconciler
from jarvis_learning.persistence.boot_session import WindowsBootDetector
from jarvis_learning.persistence.crash_matrix import CrashMatrixHarness
from jarvis_learning.persistence.durability import DurableFileWriter
from jarvis_learning.persistence.evidence_integrity import (
    AttestationKeyProvider,
    PersistenceIntegritySealer,
)
from jarvis_learning.persistence.evidence_timeline import EvidenceTimeline
from jarvis_learning.persistence.journal_verifier import DatabaseIntegrityVerifier
from jarvis_learning.persistence.lock_reclaimer import LockReclaimer
from jarvis_learning.persistence.models import (
    PointerState,
    RebootReality,
    RebootVerdict,
    TransactionState,
)
from jarvis_learning.persistence.pointer_recovery import ActivePointerManager
from jarvis_learning.persistence.post_boot_trigger import PostBootTriggerManager
from jarvis_learning.persistence.preflight import RebootSafetyPreflight
from jarvis_learning.persistence.qualification import (
    RebootQualificationDimension,
    RebootQualificationMatrix,
)
from jarvis_learning.persistence.recovery_reference import (
    ExpectedStateSnapshot,
    PersistenceReferenceModel,
)
from jarvis_learning.persistence.sqlite_recovery import SQLiteRecoveryEngine
from jarvis_learning.persistence.transaction import RebootTransactionManager

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RebootHarnessResult:
    """Master result envelope returned by RebootPersistenceHarness."""

    success: bool
    verdict: RebootVerdict
    evidence_level: EvidenceLevel
    reboot_reality: RebootReality
    transaction_id: str
    qualification: RebootQualificationMatrix
    timeline: dict[str, Any]
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "verdict": self.verdict.value,
            "evidence_level": self.evidence_level.value,
            "reboot_reality": self.reboot_reality.value,
            "transaction_id": self.transaction_id,
            "qualification": self.qualification.to_dict(),
            "timeline": self.timeline,
            "details": self.details,
        }


class RebootPersistenceHarness:
    """Master orchestrator for bare-metal reboot persistence and durability validation."""

    EVIDENCE_FILE = "post_reboot_evidence.json"
    TIMELINE_FILE = "timeline.json"
    ORACLE_FILE = "expected_oracle.json"

    @classmethod
    def arm_pre_reboot(
        cls,
        lab_dir: Path,
        trigger_task: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Phase 1: Arm system for physical reboot validation."""
        lab_dir.mkdir(parents=True, exist_ok=True)

        # 1. Safety Preflight
        preflight_passed, preflight_report = RebootSafetyPreflight.run_all_preflights(lab_dir)
        if not preflight_passed:
            return (
                False,
                f"Safety preflight failed: {preflight_report.get('failure_reason')}",
                preflight_report,
            )

        # 2. Capture baseline boot identity
        pre_boot_session = WindowsBootDetector.capture_identity()

        # 3. Create transaction with anti-replay nonce
        tx = RebootTransactionManager.create_transaction(pre_boot_session, metadata=metadata)
        RebootTransactionManager.save_transaction(tx, lab_dir)

        # 4. Initialize chronological event timeline
        timeline = EvidenceTimeline(tx.transaction_id, pre_boot_session.boot_session_id)
        timeline.record_event("TRANSACTION_ARMED", {"run_id": tx.run_id, "host_id": tx.host_id})

        # 5. Populate durable workload
        artifacts_dir = lab_dir / "artifacts"
        staging_dir = lab_dir / "_staging"
        db_dir = lab_dir / "db"
        locks_dir = lab_dir / "locks"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        staging_dir.mkdir(parents=True, exist_ok=True)
        db_dir.mkdir(parents=True, exist_ok=True)
        locks_dir.mkdir(parents=True, exist_ok=True)

        # Write durable committed Gen 1 model
        gen1_bytes = b"JARVIS_DURABLE_WEIGHTS_GEN_1_VALIDATED_DATA"
        gen1_sha = hashlib.sha256(gen1_bytes).hexdigest()
        gen1_file = artifacts_dir / "model_v1.bin"
        DurableFileWriter.write_durable(gen1_file, gen1_bytes)

        # Write commit ledger
        (artifacts_dir / "commit_ledger.json").write_text(
            json.dumps(
                {
                    "generation": 1,
                    "artifact_id": "model_v1",
                    "sha256": gen1_sha,
                    "committed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "transaction_id": tx.transaction_id,
                }
            ),
            encoding="utf-8",
        )

        # Write active pointer
        ActivePointerManager.write_pointer(
            lab_dir,
            PointerState(
                generation=1,
                artifact_id="model_v1",
                sha256=gen1_sha,
                committed_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                transaction_id=tx.transaction_id,
                state="COMMITTED",
            ),
        )

        # Seed SQLite database with committed + uncommitted WAL
        db_path = db_dir / "training_journal.db"
        SQLiteRecoveryEngine.seed_test_database(db_path, committed_count=25, uncommitted_count=5)

        # Write staging uncommitted file to test forensic quarantine
        staged_file = staging_dir / "uncommitted_weights.tmp"
        DurableFileWriter.write_durable(
            staged_file, b"UNCOMMITTED_INCOMPLETE_BUFFER_SHOULD_BE_QUARANTINED"
        )

        # Write stale lockfile with simulated pre-reboot PID (using 999999 or dead PID)
        LockReclaimer.write_lock_file(
            locks_dir / "pre_reboot_worker.lock",
            pid=999999,
            transaction_id=tx.transaction_id,
            boot_session_id=pre_boot_session.boot_session_id,
            process_name="jarvis_worker",
        )

        timeline.record_event("WORKLOAD_POPULATED", {"committed_files": 1, "db_rows_committed": 25})

        # 6. Record expected state snapshot for independent reference oracle
        oracle_snapshot = ExpectedStateSnapshot(
            transaction_id=tx.transaction_id,
            expected_generation=1,
            expected_active_artifact_id="model_v1",
            expected_committed_count=1,
            expected_db_rows=25,
            expected_staging_quarantined_count=1,
        )
        (lab_dir / cls.ORACLE_FILE).write_text(
            json.dumps(oracle_snapshot.to_dict(), indent=2), encoding="utf-8"
        )

        # 7. Build and seal pre-reboot manifest
        manifest_builder = PreRebootManifestBuilder(
            tx.transaction_id, pre_boot_session.boot_session_id, active_gen=1
        )
        manifest_builder.add_file(
            lab_dir,
            "artifacts/model_v1.bin",
            gen1_sha,
            len(gen1_bytes),
            "OS_FLUSHED",
            is_committed=True,
        )
        manifest = manifest_builder.build()

        key = AttestationKeyProvider.get_or_create_key(lab_dir, pre_boot_session.machine_guid)
        sealed_manifest_dict = PersistenceIntegritySealer.seal(
            manifest.to_dict(), key, key_id="pre_boot_attestation"
        )
        (lab_dir / "pre_reboot_manifest.json").write_text(
            json.dumps(sealed_manifest_dict, indent=2), encoding="utf-8"
        )

        timeline.record_event("MANIFEST_SEALED", {"files_count": len(manifest.files)})

        # 8. Optionally register scheduled task
        task_registered = False
        task_msg = "Task registration not requested"
        if trigger_task:
            task_registered, task_msg = PostBootTriggerManager.register_one_shot_task(
                tx.transaction_id, lab_dir
            )
            timeline.record_event(
                "SCHEDULED_TASK_REGISTERED", {"success": task_registered, "details": task_msg}
            )

        # Persist timeline
        (lab_dir / cls.TIMELINE_FILE).write_text(
            json.dumps(timeline.to_dict(), indent=2), encoding="utf-8"
        )

        return (
            True,
            f"Transaction {tx.transaction_id} armed successfully. Ready for reboot.",
            {
                "transaction": tx.to_dict(),
                "pre_boot_session": pre_boot_session.to_dict(),
                "manifest_files": len(manifest.files),
                "task_registered": task_registered,
                "task_details": task_msg,
            },
        )

    @classmethod
    def verify_post_reboot(
        cls,
        lab_dir: Path,
        expected_tx_id: str | None = None,
        force_reclaim_locks: bool = True,
        is_subprocess: bool = False,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Phase 2: Post-reboot verification and multi-dimensional qualification."""
        if not lab_dir.exists():
            return False, f"Lab directory does not exist: {lab_dir}", {}

        # 1. Load active transaction
        tx = RebootTransactionManager.load_transaction(lab_dir)
        if tx is None:
            return False, "No active transaction found in lab directory", {}

        if expected_tx_id and tx.transaction_id != expected_tx_id:
            return (
                False,
                f"Transaction ID mismatch: expected {expected_tx_id}, found {tx.transaction_id}",
                {},
            )

        # 2. Capture post-boot session identity
        post_boot_session = WindowsBootDetector.capture_identity()

        # 3. Load timeline
        timeline_path = lab_dir / cls.TIMELINE_FILE
        if timeline_path.exists():
            timeline = EvidenceTimeline.from_dict(
                json.loads(timeline_path.read_text(encoding="utf-8"))
            )
        else:
            timeline = EvidenceTimeline(tx.transaction_id, tx.pre_boot_session_id)

        timeline.record_event(
            "POST_BOOT_VERIFICATION_STARTED", {"current_boot_id": post_boot_session.boot_session_id}
        )

        # 4. Check boot reality & causality
        boot_advanced = (
            post_boot_session.boot_session_id != tx.pre_boot_session_id
            and post_boot_session.machine_guid == tx.host_id
        )

        reboot_reality = RebootReality.REAL_REBOOT if boot_advanced else RebootReality.SAME_SESSION

        # 5. Validate transaction state
        tx_valid, tx_msg = RebootTransactionManager.validate_for_verification(tx, post_boot_session)
        if not tx_valid and tx.state != TransactionState.ARMED:
            # If already verified or expired
            logger.warning("Transaction validation note: %s", tx_msg)

        # 6. Reconcile artifacts & quarantine staging
        manifest_path = lab_dir / "pre_reboot_manifest.json"
        if not manifest_path.exists():
            return False, "Missing pre_reboot_manifest.json", {}

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = PreRebootManifest.from_dict(manifest_data)

        reconcile_audit = ArtifactReconciler.reconcile(lab_dir, manifest, tx.transaction_id)
        timeline.record_event(
            "ARTIFACTS_RECONCILED",
            {
                "committed_verified": len(reconcile_audit.committed_verified),
                "quarantined": len(reconcile_audit.quarantine_records),
            },
        )

        # 7. Verify pointer & execute rollback if necessary
        effective_ptr, ptr_status, rolled_back = ActivePointerManager.verify_and_recover(lab_dir)
        pointer_ok = effective_ptr is not None and effective_ptr.generation == 1
        timeline.record_event("POINTER_AUDITED", {"status": ptr_status, "rolled_back": rolled_back})

        # 8. Audit SQLite PRAGMAs & WAL recovery
        db_path = lab_dir / "db" / "training_journal.db"
        sqlite_audit = DatabaseIntegrityVerifier.audit_database(db_path)
        sqlite_recovery = SQLiteRecoveryEngine.verify_recovery(db_path, expected_committed=25)
        sqlite_ok = sqlite_audit.is_healthy and sqlite_recovery["is_consistent"]
        timeline.record_event(
            "SQLITE_AUDITED",
            {
                "healthy": sqlite_audit.is_healthy,
                "consistent": sqlite_recovery["is_consistent"],
            },
        )

        # 9. Reclaim stale pre-reboot locks
        lock_path = lab_dir / "locks" / "pre_reboot_worker.lock"
        lock_result = LockReclaimer.audit_and_reclaim(
            lock_path,
            current_boot_session_id=post_boot_session.boot_session_id,
            force_if_stale=force_reclaim_locks,
        )
        lock_ok = lock_result.reclaimed or not lock_path.exists()
        timeline.record_event(
            "LOCKS_AUDITED", {"reclaimed": lock_result.reclaimed, "reason": lock_result.reason}
        )

        # 10. Check against independent reference oracle
        oracle_path = lab_dir / cls.ORACLE_FILE
        oracle_ok = True
        oracle_discrepancies: list[str] = []
        if oracle_path.exists():
            oracle_data = json.loads(oracle_path.read_text(encoding="utf-8"))
            expected_snapshot = ExpectedStateSnapshot(**oracle_data)
            oracle_ok, oracle_discrepancies = PersistenceReferenceModel.evaluate(
                expected=expected_snapshot,
                observed_generation=effective_ptr.generation if effective_ptr else None,
                observed_active_artifact_id=effective_ptr.artifact_id if effective_ptr else None,
                observed_committed_verified_count=len(reconcile_audit.committed_verified),
                observed_db_rows=sqlite_recovery["total_rows"],
                observed_quarantined_count=len(reconcile_audit.quarantine_records),
            )

        # 11. Cryptographic integrity & attestation check
        key = AttestationKeyProvider.get_or_create_key(lab_dir, tx.host_id)
        crypto_valid, crypto_msg = PersistenceIntegritySealer.verify(manifest_data, key)
        chain_valid, chain_msg = timeline.verify_chain()
        crypto_ok = crypto_valid and chain_valid

        # 12. Evaluate 8-dimension qualification matrix
        filesystem_ok = (
            reconcile_audit.all_committed_intact and reconcile_audit.all_staging_quarantined
        )
        physical_reboot_ok = boot_advanced and (
            tx.state in (TransactionState.ARMED, TransactionState.VERIFIED)
        )

        qualification = RebootQualificationMatrix.evaluate(
            boot_boundary_advanced=boot_advanced,
            boot_boundary_details=f"Pre: {tx.pre_boot_session_id[:8]}, Post: {post_boot_session.boot_session_id[:8]}",
            filesystem_ok=filesystem_ok,
            filesystem_details=f"Committed intact: {len(reconcile_audit.committed_verified)}, Quarantined: {len(reconcile_audit.quarantine_records)}",
            sqlite_ok=sqlite_ok,
            sqlite_details=f"PRAGMAs ok: {sqlite_audit.is_healthy}, WAL consistent: {sqlite_recovery['is_consistent']}",
            pointer_ok=pointer_ok,
            pointer_details=f"Pointer status: {ptr_status}",
            lock_ok=lock_ok,
            lock_details=f"Lock status: {lock_result.reason}",
            crypto_ok=crypto_ok,
            crypto_details=f"Manifest sig: {crypto_msg}, Chain: {chain_msg}",
            physical_reboot_confirmed=physical_reboot_ok,
            physical_reboot_details="Physical reboot causality confirmed"
            if physical_reboot_ok
            else "Tested within same boot session",
        )

        verdict = qualification.determine_verdict()
        evidence_level = qualification.determine_evidence_level(is_subprocess=is_subprocess)

        # 13. Transition transaction state to VERIFIED and consume nonce
        if reboot_reality == RebootReality.REAL_REBOOT:
            RebootTransactionManager.transition_state(tx, TransactionState.VERIFIED, lab_dir)

        # 14. Remove scheduled task if registered
        PostBootTriggerManager.remove_task(tx.transaction_id)

        timeline.record_event(
            "QUALIFICATION_COMPLETED",
            {
                "verdict": verdict.value,
                "evidence_level": evidence_level.value,
            },
        )
        (lab_dir / cls.TIMELINE_FILE).write_text(
            json.dumps(timeline.to_dict(), indent=2), encoding="utf-8"
        )

        # 15. Construct and seal final evidence payload
        evidence_payload: dict[str, Any] = {
            "transaction_id": tx.transaction_id,
            "run_id": tx.run_id,
            "host_id": tx.host_id,
            "reboot_reality": reboot_reality.value,
            "verdict": verdict.value,
            "evidence_level": evidence_level.value,
            "qualification": qualification.to_dict(),
            "oracle_check": {"passed": oracle_ok, "discrepancies": oracle_discrepancies},
            "sqlite_audit": sqlite_audit.to_dict(),
            "reconciliation": reconcile_audit.to_dict(),
            "timeline": timeline.to_dict(),
            "verified_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        sealed_evidence = PersistenceIntegritySealer.seal(
            evidence_payload, key, key_id="post_boot_attestation"
        )
        (lab_dir / cls.EVIDENCE_FILE).write_text(
            json.dumps(sealed_evidence, indent=2), encoding="utf-8"
        )

        success = verdict == RebootVerdict.PASS
        msg = (
            f"Post-reboot verification {verdict.value} (Evidence: {evidence_level.value}, "
            f"Reality: {reboot_reality.value})"
        )

        return success, msg, sealed_evidence

    @classmethod
    def run_in_suite_audit(
        cls,
        lab_dir: Path,
        is_subprocess: bool = False,
    ) -> RebootHarnessResult:
        """Execute complete self-contained in-suite durability audit and crash simulation."""
        lab_dir.mkdir(parents=True, exist_ok=True)

        # 1. Arm
        arm_ok, arm_msg, arm_info = cls.arm_pre_reboot(lab_dir, trigger_task=False)
        if not arm_ok:
            raise RuntimeError(f"In-suite arming failed: {arm_msg}")

        # 2. Run 10-point crash matrix in subfolder
        crash_results = CrashMatrixHarness.run_all(base_dir=lab_dir / "crash_matrix")
        all_crashes_passed = all(r.recovery_passed for r in crash_results)

        # 3. Execute verification in same session
        ver_ok, ver_msg, evidence = cls.verify_post_reboot(
            lab_dir,
            is_subprocess=is_subprocess,
        )

        qual_dict = evidence["qualification"]
        qual_dims = {
            dim_k: RebootQualificationDimension(**dim_v)
            for dim_k, dim_v in qual_dict["dimensions"].items()
        }
        qual = RebootQualificationMatrix(
            boot_boundary=qual_dims["boot_boundary"],
            filesystem_recovery=qual_dims["filesystem_recovery"],
            sqlite_recovery=qual_dims["sqlite_recovery"],
            pointer_recovery=qual_dims["pointer_recovery"],
            lock_recovery=qual_dims["lock_recovery"],
            cryptographic_integrity=qual_dims["cryptographic_integrity"],
            physical_reboot=qual_dims["physical_reboot"],
            power_loss=qual_dims["power_loss"],
        )

        return RebootHarnessResult(
            success=ver_ok and all_crashes_passed,
            verdict=RebootVerdict(evidence["verdict"]),
            evidence_level=EvidenceLevel(evidence["evidence_level"]),
            reboot_reality=RebootReality(evidence["reboot_reality"]),
            transaction_id=evidence["transaction_id"],
            qualification=qual,
            timeline=evidence["timeline"],
            details={
                "all_crashes_passed": all_crashes_passed,
                "crash_points_tested": len(crash_results),
                "crash_matrix": [r.to_dict() for r in crash_results],
                "evidence_path": str(lab_dir / cls.EVIDENCE_FILE),
            },
        )


__all__ = [
    "RebootHarnessResult",
    "RebootPersistenceHarness",
]
