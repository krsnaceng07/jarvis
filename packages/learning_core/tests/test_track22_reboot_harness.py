"""Dedicated comprehensive test suite for Track 2.2 Bare-Metal Reboot Persistence & Journal Harness.

Covers all 20 specification tests:
- BOOT-001: Same-session detection
- BOOT-002: Real reboot detection
- BOOT-003: Wrong-host detection
- BOOT-004: Expired transaction detection
- BOOT-005: Anti-replay nonce consumption
- FS-001: Committed artifact recovery SHA-256 verification
- FS-002: Forensic quarantine preserves uncommitted files (never silent delete)
- FS-003: Pointer epoch recovery and rollback
- DB-001: SQLite PRAGMA audits
- DB-002: Uncommitted WAL transaction discard
- DB-003: Committed WAL transaction persistence
- LOCK-001: Dead PID lock reclamation
- LOCK-002: Live process lock preservation
- CRASH-001: 10-point atomic crash matrix recovery
- DUR-001: OS-level durability flush
- ORACLE-001: Independent reference oracle discrepancy detection
- PREFLIGHT-001: Safety preflight validation
- TASK-001: Windows scheduled task command generation
- QUAL-001: Strict L6 denial on same-session execution
- HARNESS-001: Master in-suite durability audit end-to-end
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


from jarvis_learning.invariants_p10 import EvidenceLevel
from jarvis_learning.persistence.artifact_manifest import (
    FileInventoryEntry,
    PreRebootManifest,
)
from jarvis_learning.persistence.artifact_reconciler import ArtifactReconciler
from jarvis_learning.persistence.boot_session import BootSessionIdentity, WindowsBootDetector
from jarvis_learning.persistence.crash_matrix import CrashMatrixHarness
from jarvis_learning.persistence.durability import DurableFileWriter, FileSystemFlushVerifier
from jarvis_learning.persistence.journal_verifier import DatabaseIntegrityVerifier
from jarvis_learning.persistence.lock_reclaimer import LockReclaimer
from jarvis_learning.persistence.models import (
    PointerState,
    RebootVerdict,
    TransactionState,
)
from jarvis_learning.persistence.pointer_recovery import ActivePointerManager
from jarvis_learning.persistence.post_boot_trigger import PostBootTriggerManager
from jarvis_learning.persistence.preflight import RebootSafetyPreflight
from jarvis_learning.persistence.qualification import RebootQualificationMatrix
from jarvis_learning.persistence.reboot_harness import RebootPersistenceHarness
from jarvis_learning.persistence.recovery_reference import (
    ExpectedStateSnapshot,
    PersistenceReferenceModel,
)
from jarvis_learning.persistence.sqlite_recovery import SQLiteRecoveryEngine
from jarvis_learning.persistence.transaction import RebootTransactionManager


def _mock_boot_session(
    session_id: str, boot_epoch: float, guid: str = "GUID-1234"
) -> BootSessionIdentity:
    return BootSessionIdentity(
        boot_session_id=session_id,
        last_boot_up_time_utc="2026-09-19T10:00:00Z",
        last_boot_up_time_timestamp=boot_epoch,
        tick_count_ms=100000,
        machine_guid=guid,
        system_drive_serial="SERIAL-1",
        hostname="TEST-HOST",
        os_version="10.0.26100",
        captured_at_utc="2026-09-19T10:00:00Z",
    )


def test_boot_001_same_session_detection(tmp_path: Path):
    """BOOT-001: Same-session detection correctly identifies un-rebooted host."""
    session1 = _mock_boot_session("sess_alpha", 1000.0)
    session2 = _mock_boot_session("sess_alpha", 1000.0)

    reality, advanced = WindowsBootDetector.evaluate_reboot_reality(session1, session2)
    assert not advanced
    assert reality.value == "SAME_SESSION"


def test_boot_002_real_reboot_detection(tmp_path: Path):
    """BOOT-002: Real reboot detection confirms boot advance when post-boot time advances."""
    pre_sess = _mock_boot_session("sess_alpha", 1000.0)
    post_sess = _mock_boot_session("sess_beta", 2000.0)

    reality, advanced = WindowsBootDetector.evaluate_reboot_reality(pre_sess, post_sess)
    assert advanced
    assert reality.value == "REAL_REBOOT"


def test_boot_003_wrong_host_detection(tmp_path: Path):
    """BOOT-003: Wrong-host detection rejects manifest from mismatched machine GUID."""
    pre_sess = _mock_boot_session("sess_alpha", 1000.0, guid="HOST-A")
    post_sess = _mock_boot_session("sess_beta", 2000.0, guid="HOST-B")

    tx = RebootTransactionManager.create_transaction(pre_sess)
    valid, msg = RebootTransactionManager.validate_for_verification(tx, post_sess)
    assert not valid
    assert "Host ID mismatch" in msg


def test_boot_004_expired_transaction_detection(tmp_path: Path):
    """BOOT-004: Expired transaction detection blocks verification past valid window."""
    pre_sess = _mock_boot_session("sess_alpha", 1000.0)
    tx = RebootTransactionManager.create_transaction(pre_sess, expected_window_seconds=10.0)

    # Validate expired with simulated future epoch
    future_epoch = tx.arm_timestamp_epoch + 15.0
    assert tx.is_expired(current_epoch=future_epoch)


def test_boot_005_anti_replay_nonce_consumption(tmp_path: Path):
    """BOOT-005: Anti-replay nonce prevents duplicate verification of same transaction."""
    pre_sess = _mock_boot_session("sess_alpha", 1000.0)
    tx = RebootTransactionManager.create_transaction(pre_sess)
    RebootTransactionManager.save_transaction(tx, tmp_path)

    # Transition to verified
    updated_tx = RebootTransactionManager.transition_state(tx, TransactionState.VERIFIED, tmp_path)
    assert updated_tx.nonce.startswith("CONSUMED_")
    assert updated_tx.state == TransactionState.VERIFIED

    # Check that subsequent validation fails because state is no longer ARMED
    valid, msg = RebootTransactionManager.validate_for_verification(updated_tx, pre_sess)
    assert not valid
    assert "Invalid transaction state: VERIFIED" in msg


def test_fs_001_committed_artifact_recovery_sha256(tmp_path: Path):
    """FS-001: Committed artifact recovery verifies bit-for-bit SHA-256 integrity."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True)
    file_bytes = b"VERIFIED_PERSISTENT_PAYLOAD"
    file_sha = hashlib.sha256(file_bytes).hexdigest()
    art_file = artifacts_dir / "model.bin"
    art_file.write_bytes(file_bytes)

    manifest = PreRebootManifest(
        manifest_version="1.0.0",
        transaction_id="TX-FS1",
        created_at_utc="2026-09-19T10:00:00Z",
        boot_session_id="sess-1",
        active_generation=1,
        files=[
            FileInventoryEntry(
                relative_path="artifacts/model.bin",
                sha256_digest=file_sha,
                file_size_bytes=len(file_bytes),
                durability_level="OS_FLUSHED",
                is_committed=True,
            )
        ],
        manifest_signature="",
    )

    audit = ArtifactReconciler.reconcile(tmp_path, manifest, "TX-FS1")
    assert audit.all_committed_intact
    assert "artifacts/model.bin" in audit.committed_verified
    assert len(audit.committed_corrupt) == 0


def test_fs_002_forensic_quarantine_preserves_files(tmp_path: Path):
    """FS-002: Forensic quarantine moves uncommitted staging files to _quarantine/ without deletion."""
    staging_dir = tmp_path / "_staging"
    staging_dir.mkdir(parents=True)
    broken_file = staging_dir / "uncommitted_broken.tmp"
    broken_file.write_bytes(b"TEMPORARY_CRASH_GARBAGE")

    manifest = PreRebootManifest(
        manifest_version="1.0.0",
        transaction_id="TX-FS2",
        created_at_utc="2026-09-19T10:00:00Z",
        boot_session_id="sess-1",
        active_generation=1,
        files=[],
        manifest_signature="",
    )

    audit = ArtifactReconciler.reconcile(tmp_path, manifest, "TX-FS2")
    assert audit.all_staging_quarantined
    assert len(audit.quarantine_records) == 1
    # Check that file was NOT deleted, but moved to _quarantine/TX-FS2/
    quarantine_path = tmp_path / audit.quarantine_records[0].quarantined_path
    assert quarantine_path.exists()
    assert quarantine_path.read_bytes() == b"TEMPORARY_CRASH_GARBAGE"


def test_fs_003_pointer_epoch_rollback_on_corruption(tmp_path: Path):
    """FS-003: Pointer epoch recovery successfully rolls back to previous valid generation on corruption."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True)

    # Durable Gen 1
    gen1_bytes = b"GEN_1_DATA"
    gen1_sha = hashlib.sha256(gen1_bytes).hexdigest()
    (artifacts_dir / "gen1.bin").write_bytes(gen1_bytes)
    (artifacts_dir / "commit_ledger.json").write_text(
        json.dumps(
            {
                "generation": 1,
                "artifact_id": "gen1",
                "sha256": gen1_sha,
                "committed_at_utc": "2026-09-19T09:00:00Z",
                "transaction_id": "TX-0",
            }
        )
    )

    # Broken/corrupt active pointer claiming Gen 2
    ActivePointerManager.write_pointer(
        tmp_path,
        PointerState(
            generation=2,
            artifact_id="gen2_missing",
            sha256="bad_digest",
            committed_at_utc="2026-09-19T10:00:00Z",
            transaction_id="TX-1",
            state="INCOMPLETE",
        ),
    )

    ptr, reason, rolled_back = ActivePointerManager.verify_and_recover(tmp_path)
    assert rolled_back
    assert ptr is not None
    assert ptr.generation == 1
    assert ptr.artifact_id == "gen1"
    assert "ROLLED_BACK" in reason


def test_db_001_sqlite_pragma_auditing(tmp_path: Path):
    """DB-001: SQLite PRAGMA integrity check and foreign key check pass cleanly."""
    db_path = tmp_path / "test_pragma.db"
    SQLiteRecoveryEngine.seed_test_database(db_path, committed_count=20, uncommitted_count=0)

    report = DatabaseIntegrityVerifier.audit_database(db_path)
    assert report.is_healthy
    assert report.integrity_check_passed
    assert report.quick_check_passed
    assert report.foreign_keys_passed
    assert report.journal_mode.upper() == "WAL"


def test_db_002_sqlite_uncommitted_wal_discard(tmp_path: Path):
    """DB-002: Uncommitted SQLite transactions in WAL are discarded without corruption."""
    db_path = tmp_path / "test_wal_uncommitted.db"
    # Seed 15 committed, 10 uncommitted in active WAL
    SQLiteRecoveryEngine.seed_test_database(db_path, committed_count=15, uncommitted_count=10)

    recovery = SQLiteRecoveryEngine.verify_recovery(db_path, expected_committed=15)
    assert recovery["is_consistent"]
    assert recovery["clean_rollback"]
    assert recovery["uncommitted_present"] == 0
    assert recovery["total_rows"] == 15


def test_db_003_sqlite_committed_wal_durability(tmp_path: Path):
    """DB-003: Committed SQLite transactions survive crash and are recovered."""
    db_path = tmp_path / "test_wal_committed.db"
    SQLiteRecoveryEngine.seed_test_database(db_path, committed_count=50, uncommitted_count=0)

    recovery = SQLiteRecoveryEngine.verify_recovery(db_path, expected_committed=50)
    assert recovery["is_consistent"]
    assert recovery["committed_intact"]
    assert recovery["total_rows"] == 50


def test_lock_001_dead_pid_lock_reclaimed(tmp_path: Path):
    """LOCK-001: Stale lockfile with dead pre-reboot PID is reclaimed safely."""
    lock_file = tmp_path / "worker.lock"
    # Use non-existent PID 9999999
    LockReclaimer.write_lock_file(lock_file, pid=9999999, transaction_id="TX-LOCK1")

    res = LockReclaimer.audit_and_reclaim(lock_file, force_if_stale=True)
    assert res.is_stale
    assert res.reclaimed
    assert not lock_file.exists()


def test_lock_002_live_process_lock_preserved(tmp_path: Path):
    """LOCK-002: Live lockfile from active current-process PID is not reclaimed."""
    lock_file = tmp_path / "live_worker.lock"
    current_pid = os.getpid()
    LockReclaimer.write_lock_file(lock_file, pid=current_pid, transaction_id="TX-LOCK2")

    res = LockReclaimer.audit_and_reclaim(lock_file, force_if_stale=True)
    assert not res.is_stale
    assert not res.reclaimed
    assert lock_file.exists()


def test_crash_001_atomic_10_point_matrix(tmp_path: Path):
    """CRASH-001: Crash-point matrix recovers cleanly across all 10 persistence steps."""
    results = CrashMatrixHarness.run_all(base_dir=tmp_path)
    assert len(results) == 10
    for res in results:
        assert res.recovery_passed, f"Failed at {res.crash_point_id}: {res.notes}"


def test_dur_001_os_level_durable_flush(tmp_path: Path):
    """DUR-001: OS-level durable flush (FlushFileBuffers / os.fsync) validates."""
    target_file = tmp_path / "durable.bin"
    content = b"DURABLE_PAYLOAD_WITH_OS_FLUSH"

    level = DurableFileWriter.write_durable(target_file, content)
    assert level.value in ("ATOMIC_RENAME", "OS_FLUSHED", "USERSPACE_FLUSHED")
    assert target_file.exists()
    assert target_file.read_bytes() == content

    verifier = FileSystemFlushVerifier.verify_flush_mechanics(tmp_path)
    assert verifier["durable_write_succeeded"]


def test_oracle_001_independent_reference_model_discrepancy(tmp_path: Path):
    """ORACLE-001: Independent reference model catches discrepancy even if SQLite returns ok."""
    expected = ExpectedStateSnapshot(
        transaction_id="TX-ORACLE",
        expected_generation=2,
        expected_active_artifact_id="model_v2",
        expected_committed_count=3,
        expected_db_rows=100,
        expected_staging_quarantined_count=0,
    )

    # Observed mismatch: db rows is 90 instead of 100
    is_ok, discrepancies = PersistenceReferenceModel.evaluate(
        expected=expected,
        observed_generation=2,
        observed_active_artifact_id="model_v2",
        observed_committed_verified_count=3,
        observed_db_rows=90,
        observed_quarantined_count=0,
    )
    assert not is_ok
    assert any("Database rows mismatch" in d for d in discrepancies)


def test_preflight_001_safety_preflight(tmp_path: Path):
    """PREFLIGHT-001: Safety preflight blocks arming if disk space is low or active training running."""
    # Healthy preflight
    ok, report = RebootSafetyPreflight.run_all_preflights(tmp_path)
    assert ok
    assert report["all_passed"]

    # Injected failure: low disk space limit
    report_low = RebootSafetyPreflight.check_disk_space(tmp_path, min_free_bytes=10**18)
    assert not report_low["passed"]


def test_task_001_windows_scheduled_task_command_generation(tmp_path: Path):
    """TASK-001: One-shot Windows Scheduled Task command generation syntax."""
    cmd = PostBootTriggerManager.build_create_command(
        task_name="JARVIS_Track22_TX1",
        python_exe="python.exe",
        script_path=Path("tools/scripts/run_reboot_lab.py"),
        lab_dir=tmp_path,
        transaction_id="TX1",
    )
    assert "schtasks" in cmd[0]
    assert "/create" in cmd
    assert "JARVIS_Track22_TX1" in cmd
    assert "/sc" in cmd and "ONLOGON" in cmd

    del_cmd = PostBootTriggerManager.build_delete_command("JARVIS_Track22_TX1")
    assert "/delete" in del_cmd
    assert "/f" in del_cmd


def test_qual_001_strict_l6_denial_on_same_session(tmp_path: Path):
    """QUAL-001: Multi-dimensional gate strictly denies L6 if reboot was within same session."""
    qual = RebootQualificationMatrix.evaluate(
        boot_boundary_advanced=False,  # Same session!
        boot_boundary_details="Same session test",
        filesystem_ok=True,
        filesystem_details="Committed ok",
        sqlite_ok=True,
        sqlite_details="DB ok",
        pointer_ok=True,
        pointer_details="Pointer ok",
        lock_ok=True,
        lock_details="Lock ok",
        crypto_ok=True,
        crypto_details="Crypto ok",
        physical_reboot_confirmed=False,
        physical_reboot_details="No physical reboot",
    )

    evidence_lvl = qual.determine_evidence_level()
    assert evidence_lvl != EvidenceLevel.L6_REAL_REBOOT_SESSION
    assert evidence_lvl == EvidenceLevel.L4_REAL_WINDOWS_API
    assert not qual.is_physical_reboot_proven
    assert qual.is_durability_verified


def test_harness_001_master_in_suite_audit_end_to_end(tmp_path: Path):
    """HARNESS-001: Full in-suite durability audit executes end-to-end and produces sealed evidence."""
    lab_dir = tmp_path / "lab_harness"
    result = RebootPersistenceHarness.run_in_suite_audit(lab_dir)

    assert result.success
    assert result.verdict == RebootVerdict.PASS
    # Strictly L4 in-suite (same boot session)
    assert result.evidence_level == EvidenceLevel.L4_REAL_WINDOWS_API
    assert result.details["all_crashes_passed"]
    assert result.details["crash_points_tested"] == 10

    evidence_file = lab_dir / RebootPersistenceHarness.EVIDENCE_FILE
    assert evidence_file.exists()

    evidence_data = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert "attestation" in evidence_data
    assert evidence_data["attestation"]["hmac_sha256"] != ""
