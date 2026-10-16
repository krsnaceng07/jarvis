"""Atomic 10-point crash simulation harness for Track 2.2 persistence recovery.

Exhaustively validates system recovery across 10 atomic persistence failure points:
- CP-01: Before staging write
- CP-02: During staging write (partial / truncated file)
- CP-03: After staging flush (FlushFileBuffers) but before rename
- CP-04: Before SHA-256 verification (staging file corrupted)
- CP-05: Before atomic rename (staging valid, rename pending)
- CP-06: After atomic rename (artifact placed, pointer not updated)
- CP-07: Before pointer update (ledger written, pointer unchanged)
- CP-08: During pointer update (corrupted pointer file)
- CP-09: Before database commit (uncommitted WAL transaction)
- CP-10: During stale cleanup (extraneous staging leftover)
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from pathlib import Path
import tempfile
from typing import Any

from jarvis_learning.persistence.artifact_manifest import (
    FileInventoryEntry,
    PreRebootManifest,
)
from jarvis_learning.persistence.artifact_reconciler import ArtifactReconciler
from jarvis_learning.persistence.durability import DurableFileWriter
from jarvis_learning.persistence.pointer_recovery import ActivePointerManager
from jarvis_learning.persistence.sqlite_recovery import SQLiteRecoveryEngine

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class CrashPointResult:
    """Result of testing an individual persistence crash point."""

    crash_point_id: str
    name: str
    description: str
    recovery_passed: bool
    recovered_generation: int | None
    quarantined_count: int
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class CrashMatrixHarness:
    """Simulates 10 atomic failure points and validates recovery semantics."""

    CRASH_POINTS: list[tuple[str, str, str]] = [
        ("CP-01", "BeforeStagingWrite", "Crash before staging file is created"),
        (
            "CP-02",
            "DuringStagingWrite",
            "Crash during staging write with partial/truncated content",
        ),
        ("CP-03", "AfterStagingFlush", "Crash after staging flush before atomic rename"),
        (
            "CP-04",
            "BeforeSha256Verification",
            "Crash with corrupt staging content before verification",
        ),
        (
            "CP-05",
            "BeforeAtomicRename",
            "Crash with valid staging file before atomic rename to destination",
        ),
        (
            "CP-06",
            "AfterAtomicRename",
            "Crash after rename with artifact placed but pointer un-bumped",
        ),
        (
            "CP-07",
            "BeforePointerUpdate",
            "Crash with commit ledger in place before pointer file is updated",
        ),
        ("CP-08", "DuringPointerUpdate", "Crash during pointer file update leaving corrupt JSON"),
        ("CP-09", "BeforeDatabaseCommit", "Crash leaving uncommitted transaction frames in WAL"),
        (
            "CP-10",
            "DuringStaleCleanup",
            "Crash during post-commit cleanup leaving stale staging files",
        ),
    ]

    @classmethod
    def run_all(cls, base_dir: Path | None = None) -> list[CrashPointResult]:
        """Run all 10 crash points in isolated directories and return audit results."""
        results: list[CrashPointResult] = []
        for cp_id, name, desc in cls.CRASH_POINTS:
            res = cls.run_single_crash_point(cp_id, base_dir=base_dir)
            results.append(res)
        return results

    @classmethod
    def run_single_crash_point(
        cls,
        crash_point_id: str,
        base_dir: Path | None = None,
    ) -> CrashPointResult:
        """Simulate a specific crash point and execute full recovery."""
        temp_ctx = None
        if base_dir is None:
            temp_ctx = tempfile.TemporaryDirectory(prefix=f"jarvis_crash_{crash_point_id}_")
            root_dir = Path(temp_ctx.name)
        else:
            root_dir = base_dir / f"crash_{crash_point_id}"
            root_dir.mkdir(parents=True, exist_ok=True)

        try:
            return cls._execute_simulated_crash(crash_point_id, root_dir)
        finally:
            if temp_ctx is not None:
                temp_ctx.cleanup()

    @classmethod
    def _execute_simulated_crash(cls, cp_id: str, root_dir: Path) -> CrashPointResult:
        """Setup initial state, inject crash point condition, and invoke recovery."""
        staging_dir = root_dir / "_staging"
        artifacts_dir = root_dir / "artifacts"
        db_dir = root_dir / "db"
        staging_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        db_dir.mkdir(parents=True, exist_ok=True)

        tx_id = f"TX_{cp_id}"

        # Seed initial committed baseline: Gen 1
        gen1_content = b"Committed Generation 1 Model Weights"
        gen1_digest = hashlib.sha256(gen1_content).hexdigest()
        gen1_file = artifacts_dir / "model_gen1.bin"
        DurableFileWriter.write_durable(gen1_file, gen1_content)

        gen1_ledger = artifacts_dir / "commit_ledger.json"
        gen1_ledger.write_text(
            json.dumps(
                {
                    "generation": 1,
                    "artifact_id": "model_gen1",
                    "sha256": gen1_digest,
                    "committed_at_utc": "2026-09-19T10:00:00Z",
                    "transaction_id": "TX_INIT",
                }
            ),
            encoding="utf-8",
        )

        from jarvis_learning.persistence.models import PointerState

        ActivePointerManager.write_pointer(
            root_dir,
            PointerState(
                generation=1,
                artifact_id="model_gen1",
                sha256=gen1_digest,
                committed_at_utc="2026-09-19T10:00:00Z",
                transaction_id="TX_INIT",
                state="COMMITTED",
            ),
        )

        # Baseline manifest
        manifest = PreRebootManifest(
            manifest_version="1.0.0",
            transaction_id=tx_id,
            created_at_utc="2026-09-19T10:00:00Z",
            boot_session_id="boot_sess_1",
            active_generation=1,
            files=[
                FileInventoryEntry(
                    relative_path="artifacts/model_gen1.bin",
                    sha256_digest=gen1_digest,
                    file_size_bytes=len(gen1_content),
                    durability_level="ATOMIC_RENAME",
                    is_committed=True,
                )
            ],
            manifest_signature="",
        )

        db_path = db_dir / "test.db"
        SQLiteRecoveryEngine.seed_test_database(db_path, committed_count=10, uncommitted_count=0)

        # Inject crash condition based on cp_id
        target_name = [p[1] for p in cls.CRASH_POINTS if p[0] == cp_id][0]
        desc = [p[2] for p in cls.CRASH_POINTS if p[0] == cp_id][0]

        gen2_content = b"Candidate Generation 2 Model Weights"
        gen2_digest = hashlib.sha256(gen2_content).hexdigest()

        if cp_id == "CP-01":
            # Before staging write: nothing added
            pass

        elif cp_id == "CP-02":
            # During staging write: truncated partial file
            (staging_dir / "candidate.tmp").write_bytes(gen2_content[:10])

        elif cp_id == "CP-03":
            # After staging flush: full staging file exists, rename not performed
            DurableFileWriter.write_durable(staging_dir / "candidate.tmp", gen2_content)

        elif cp_id == "CP-04":
            # Before sha256 verification: corrupt bytes in staging
            (staging_dir / "corrupt_candidate.tmp").write_bytes(
                b"bad bytes that do not match expected"
            )

        elif cp_id == "CP-05":
            # Before atomic rename: staging file valid and flushed
            DurableFileWriter.write_durable(staging_dir / "staged_gen2.bin", gen2_content)

        elif cp_id == "CP-06":
            # After atomic rename: gen2 file placed in artifacts, but pointer remains gen1
            gen2_file = artifacts_dir / "model_gen2.bin"
            DurableFileWriter.write_durable(gen2_file, gen2_content)

        elif cp_id == "CP-07":
            # Before pointer update: gen2 ledger written, pointer remains gen1
            gen2_file = artifacts_dir / "model_gen2.bin"
            DurableFileWriter.write_durable(gen2_file, gen2_content)
            gen2_ledger_dir = artifacts_dir / "gen2_dir"
            gen2_ledger_dir.mkdir(parents=True, exist_ok=True)
            (gen2_ledger_dir / "commit_ledger.json").write_text(
                json.dumps(
                    {
                        "generation": 2,
                        "artifact_id": "model_gen2",
                        "sha256": gen2_digest,
                        "committed_at_utc": "2026-09-19T10:05:00Z",
                        "transaction_id": tx_id,
                    }
                ),
                encoding="utf-8",
            )
            # Copy bin file near ledger for ActivePointerManager discovery
            (gen2_ledger_dir / "model_gen2.bin").write_bytes(gen2_content)

        elif cp_id == "CP-08":
            # During pointer update: pointer file corrupted with truncated JSON
            pointer_path = root_dir / ActivePointerManager.POINTER_FILE
            pointer_path.write_text(
                '{"active_generation": 2, "artifact_id": "model_gen2", "sha256":', encoding="utf-8"
            )

        elif cp_id == "CP-09":
            # Before database commit: uncommitted WAL frames left in SQLite
            SQLiteRecoveryEngine.seed_test_database(
                db_path, committed_count=10, uncommitted_count=5
            )

        elif cp_id == "CP-10":
            # During stale cleanup: leftover garbage in staging
            (staging_dir / "stale_leftover_1.tmp").write_bytes(b"garbage 1")
            (staging_dir / "stale_leftover_2.tmp").write_bytes(b"garbage 2")

        # EXECUTE POST-CRASH RECOVERY
        reconcile_audit = ArtifactReconciler.reconcile(root_dir, manifest, tx_id)
        effective_ptr, reason, rolled_back = ActivePointerManager.verify_and_recover(root_dir)
        db_audit = SQLiteRecoveryEngine.verify_recovery(db_path, expected_committed=10)

        # EVALUATE RECOVERY OUTCOME
        # 1. Committed Gen 1 must always be intact
        committed_intact = reconcile_audit.all_committed_intact and (gen1_file.exists())
        # 2. Database must be consistent (no uncommitted WAL rows)
        db_consistent = db_audit["is_consistent"]
        # 3. Active pointer must be valid (either Gen 1 or valid Gen 2)
        ptr_valid = effective_ptr is not None and effective_ptr.generation in (1, 2)
        # 4. Any staging file must have been quarantined (not silently deleted)
        staging_quarantined = reconcile_audit.all_staging_quarantined

        passed = committed_intact and db_consistent and ptr_valid and staging_quarantined
        recovered_gen = effective_ptr.generation if effective_ptr else None

        notes = (
            f"Status: {reason} | DB clean: {db_consistent} | "
            f"Quarantined: {len(reconcile_audit.quarantine_records)} | "
            f"Rolled back: {rolled_back}"
        )

        return CrashPointResult(
            crash_point_id=cp_id,
            name=target_name,
            description=desc,
            recovery_passed=passed,
            recovered_generation=recovered_gen,
            quarantined_count=len(reconcile_audit.quarantine_records),
            notes=notes,
        )


__all__ = ["CrashMatrixHarness", "CrashPointResult"]
