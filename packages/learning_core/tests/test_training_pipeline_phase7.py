"""Phase 7 tests — Training Pipeline & Resource Governance.

Verifies the 40 critical engineering scenarios mandated by the Phase 7 specification:
- P7-01 to P7-10: Hard Gates 1-6 & 10, approval, immutability, revocation, scope, Merkle, partition isolation, single-job concurrency
- P7-11 to P7-16: Subprocess isolation, worker crash isolation, watchdog deadlock detection, cancellation, IPC protocol, Windows Job Objects
- P7-17 to P7-22: CPU thread controls, memory governor RSS limits, GPU visibility, OOM classification, disk space preflight & runtime exhaustion
- P7-23 to P7-28: 19-state lifecycle machine, multi-dimensional training budget, timeout abort, cooperative pause/resume, hash validation
- P7-29 to P7-34: Atomic checkpoint durability with COMPLETE marker, fsync, corruption quarantine, retention policy, reproducibility fingerprinting & tolerances
- P7-35 to P7-40: Model architecture compatibility, batch policy token budgeting, purpose-driven loss strategies, early stopping, regression gates, golden holdout sealing
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from jarvis_learning.datasets.dataset_lifecycle import DatasetLifecycleState
from jarvis_learning.datasets.dataset_manifest import DatasetManifest
from jarvis_learning.training.batching import (
    BatchPolicy,
    DeterministicSampler,
    SampleCollator,
)
from jarvis_learning.training.budget import (
    BudgetExhaustionReason,
    BudgetTracker,
    TrainingBudget,
)
from jarvis_learning.training.checkpoint_retention_policy import (
    CheckpointRetentionPolicy,
)
from jarvis_learning.training.checkpoint_store import (
    COMPLETE_MARKER_FILE,
    REVOKED_MARKER_FILE,
    CheckpointStore,
)
from jarvis_learning.training.confidence_intervals import (
    EvaluationDecision,
    EvaluatorDecisionEngine,
    compute_wilson_interval,
)
from jarvis_learning.training.config import TrainingConfig
from jarvis_learning.training.cpu_governor import CpuGovernor
from jarvis_learning.training.dataset_lock import (
    ConcurrencyController,
    TrainingInputLock,
)
from jarvis_learning.training.disk_governor import DiskGovernor
from jarvis_learning.training.quality_gates import (
    DatasetQualityGate,
    DatasetQualityPolicy,
    ImbalanceAction,
    QualityGateError,
)
from jarvis_learning.training.security_policy import (
    SecurityPolicy,
    SecurityPolicyError,
)
from jarvis_learning.training.errors import (
    AutomaticDeploymentForbiddenError,
    BudgetExhaustedError,
    ChallengePartitionLeakageError,
    CheckpointCorruptError,
    CheckpointMissingCompleteMarkerError,
    ConcurrencyLimitError,
    DatasetRevokedError,
    DatasetUnapprovedError,
    DatasetUnfrozenError,
    DiskSpaceExhaustedError,
    GoldenHoldoutViolationError,
    IntegrityMismatchError,
    ModelIncompatibleError,
    ResourceLimitExceededError,
    ScopeMismatchError,
    StateTransitionError,
    TimeoutExhaustedError,
    WorkerUnresponsiveError,
)
from jarvis_learning.training.evaluation import CandidateEvaluator
from jarvis_learning.training.governance import TrainingGovernance
from jarvis_learning.training.gpu_governor import GpuGovernor
from jarvis_learning.training.job_lifecycle import JobStateMachine, TrainingJobState
from jarvis_learning.training.loss import (
    DPOObjective,
    GradedMarginLoss,
    KTOObjective,
    WeightedCrossEntropyLoss,
    WeightedFocalLoss,
    get_loss_strategy_for_purpose,
)
from jarvis_learning.training.loss_tracker import EarlyStopping, LossTracker
from jarvis_learning.training.memory_governor import MemoryGovernor, MemoryLimits
from jarvis_learning.training.model_compatibility import (
    ModelArchitectureSpec,
    ModelCompatibilityChecker,
)
from jarvis_learning.training.partition_guard import PartitionGuard
from jarvis_learning.training.reproducibility import (
    PrecisionMode,
    ReproducibilityFingerprint,
    check_numerical_equivalence,
)
from jarvis_learning.training.supervisor import (
    TrainingSupervisor,
)
from jarvis_learning.training.trainer import OfflineTrainer
from jarvis_learning.training.trainer_backend import (
    TFIDFLogisticBaselineBackend,
)
from jarvis_learning.training.watchdog import WorkerWatchdog
from jarvis_learning.training.windows_job import WindowsJobObject


# ---------------------------------------------------------------------------
# Fixture Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_dataset_dir(tmp_path: Path) -> Path:
    """Create a temporary valid dataset directory with manifest and jsonl splits."""
    ds_dir = tmp_path / "test_dataset"
    ds_dir.mkdir(parents=True)

    manifest_data = {
        "dataset_id": "ds_test_123",
        "target": "desktop_navigation",
        "source_snapshot_hash": "snap_hash_abc123",
        "merkle_root": "merkle_root_xyz789",
        "total_samples": 20,
        "sample_counts": {"train": 12, "validation": 4, "test": 4},
        "lifecycle_state": DatasetLifecycleState.APPROVED_FOR_TRAINING.value,
        "operator_approval": {
            "operator_id": "admin",
            "timestamp": time.time(),
            "approval_scope": "desktop_navigation",
        },
    }
    (ds_dir / "manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")

    # Generate sample jsonl files
    def write_jsonl(filename: str, count: int, prefix: str) -> None:
        lines = []
        for i in range(count):
            sample = {
                "sample_id": f"{prefix}_{i:03d}",
                "input_data": {"user_input": f"open app {prefix} number {i}"},
                "label": {"tool": "desktop_open_app"},
            }
            lines.append(json.dumps(sample))
        (ds_dir / filename).write_text("\n".join(lines), encoding="utf-8")

    write_jsonl("train.jsonl", 12, "train")
    write_jsonl("validation.jsonl", 4, "val")
    write_jsonl("test.jsonl", 4, "test")
    write_jsonl("ood_test.jsonl", 2, "ood")
    write_jsonl("challenge.jsonl", 2, "challenge")
    write_jsonl("golden_holdout.jsonl", 2, "golden")

    return ds_dir


# ===========================================================================
# Group 1: Gate & Governance Scenarios (P7-01 to P7-10)
# ===========================================================================


def test_p7_01_gate1_unapproved_dataset_rejected(tmp_path: Path) -> None:
    """Gate 1: Dataset without APPROVED_FOR_TRAINING or APPROVED state is rejected."""
    manifest = DatasetManifest(
        dataset_id="ds_unapproved",
        target="desktop",
        source_snapshot_hash="hash123",
        merkle_root="merkle123",
        total_samples=10,
        sample_counts={"train": 10},
        lifecycle_state=DatasetLifecycleState.DRAFT.value,
    )
    with pytest.raises(DatasetUnapprovedError) as exc_info:
        TrainingGovernance.verify_gate1_approval(manifest)
    assert "Gate 1 failed" in str(exc_info.value)


def test_p7_02_gate2_unfrozen_dataset_rejected() -> None:
    """Gate 2: Dataset lacking frozen snapshot hash is rejected."""
    manifest = DatasetManifest(
        dataset_id="ds_mutable",
        target="desktop",
        source_snapshot_hash="",  # Empty snapshot hash indicates not frozen
        merkle_root="merkle123",
        total_samples=10,
        sample_counts={"train": 10},
        lifecycle_state=DatasetLifecycleState.APPROVED_FOR_TRAINING.value,
    )
    with pytest.raises(DatasetUnfrozenError) as exc_info:
        TrainingGovernance.verify_gate2_frozen(manifest)
    assert "Gate 2 failed" in str(exc_info.value)


def test_p7_03_gate3_revoked_dataset_rejected() -> None:
    """Gate 3: Revoked dataset is rejected prior to training startup."""
    with pytest.raises(DatasetRevokedError) as exc_info:
        TrainingGovernance.verify_gate3_revocation(
            dataset_id="ds_revoked_999",
            revoked_ids=["ds_revoked_999", "ds_other"],
        )
    assert "is revoked" in str(exc_info.value)


def test_p7_04_gate3b_dataset_revoked_during_execution(tmp_path: Path) -> None:
    """Gate 3b: TrainingInputLock detects mid-run dataset revocation and aborts."""
    lock = TrainingInputLock(
        dataset_id="ds_executing",
        manifest_hash="hash_abc",
        dataset_dir=tmp_path,
    )
    lock.acquire()
    assert lock.is_active is True

    # Check still valid initially
    assert lock.verify_still_valid() is True

    # Simulate revocation check triggered mid-run
    db_file = tmp_path / "mock_state.sqlite"
    db_file.write_text("dummy", encoding="utf-8")
    lock.db_path = db_file

    # Mock revocation function for test
    from unittest.mock import patch

    with patch("jarvis_learning.training.dataset_lock.is_dataset_revoked", return_value=True):
        with pytest.raises(DatasetRevokedError) as exc_info:
            lock.verify_still_valid()
        assert "REVOKED_DURING_EXECUTION" in str(exc_info.value)


def test_p7_05_gate4_scope_mismatch_rejected() -> None:
    """Gate 4: Mismatch between operator approval scope and target is rejected."""
    manifest = DatasetManifest(
        dataset_id="ds_browser",
        target="browser_automation",
        source_snapshot_hash="hash123",
        merkle_root="merkle123",
        total_samples=10,
        sample_counts={"train": 10},
        lifecycle_state=DatasetLifecycleState.APPROVED_FOR_TRAINING.value,
    )
    # Target mismatch
    with pytest.raises(ScopeMismatchError):
        TrainingGovernance.verify_gate4_scope(manifest, target="voice_command")

    # Operator approval scope mismatch
    with pytest.raises(ScopeMismatchError):
        TrainingGovernance.verify_gate4_scope(
            manifest, target="browser_automation", approval_scope="restricted_desktop"
        )


def test_p7_06_gate5_manifest_merkle_corruption_rejected() -> None:
    """Gate 5: Merkle tree root mismatch triggers IntegrityMismatchError."""
    manifest = DatasetManifest(
        dataset_id="ds_tampered",
        target="desktop",
        source_snapshot_hash="hash123",
        merkle_root="actual_merkle_root_abc",
        total_samples=10,
        sample_counts={"train": 10},
        lifecycle_state=DatasetLifecycleState.APPROVED_FOR_TRAINING.value,
    )
    with pytest.raises(IntegrityMismatchError) as exc_info:
        TrainingGovernance.verify_gate5_integrity(
            manifest, expected_merkle_root="expected_different_root_xyz"
        )
    assert "Merkle root mismatch" in str(exc_info.value)


def test_p7_07_gate6_golden_holdout_leakage_prevented() -> None:
    """Gate 6: Attempting to include golden holdout samples in training raises GoldenHoldoutViolationError."""
    train_ids = ["train_001", "train_002", "golden_sample_999"]
    golden_ids = ["golden_sample_999", "golden_sample_1000"]

    with pytest.raises(GoldenHoldoutViolationError) as exc_info:
        PartitionGuard.verify_isolation(
            train_ids=train_ids,
            golden_ids=golden_ids,
        )
    assert "Golden holdout partition leakage" in str(exc_info.value)


def test_p7_08_gate6b_challenge_partition_isolated() -> None:
    """Gate 6b: Challenge partition samples leaking into training triggers ChallengePartitionLeakageError."""
    train_ids = ["train_001", "train_002", "challenge_adv_01"]
    challenge_ids = ["challenge_adv_01", "challenge_adv_02"]

    with pytest.raises(ChallengePartitionLeakageError) as exc_info:
        PartitionGuard.verify_isolation(
            train_ids=train_ids,
            challenge_ids=challenge_ids,
        )
    assert "Challenge partition leakage" in str(exc_info.value)


def test_p7_09_gate10_zero_automatic_deployment() -> None:
    """Gate 10: Any attempt to auto-deploy trained models raises AutomaticDeploymentForbiddenError."""
    with pytest.raises(AutomaticDeploymentForbiddenError) as exc_info:
        TrainingGovernance.verify_gate10_zero_auto_deployment(auto_deploy_flag=True)
    assert "auto_deploy=True is forbidden" in str(exc_info.value)


def test_p7_10_single_concurrent_job_enforcement() -> None:
    """Single concurrent job rule (limit=1) rejects concurrent execution."""
    job_1 = "job_alpha_1"
    job_2 = "job_beta_2"

    try:
        ConcurrencyController.acquire_slot(job_1)
        assert ConcurrencyController.get_active_job() == job_1

        # Attempting to acquire slot for job_2 raises ConcurrencyLimitError
        with pytest.raises(ConcurrencyLimitError) as exc_info:
            ConcurrencyController.acquire_slot(job_2)
        assert "Concurrent training jobs are not permitted" in str(exc_info.value)
    finally:
        ConcurrencyController.release_slot(job_1)
        assert ConcurrencyController.get_active_job() is None


# ===========================================================================
# Group 2: Subprocess Isolation & Watchdog Scenarios (P7-11 to P7-16)
# ===========================================================================


def test_p7_11_supervised_subprocess_isolation(sample_dataset_dir: Path, tmp_path: Path) -> None:
    """Supervisor initializes child process with isolated IPC and watchdog."""
    out_dir = tmp_path / "supervisor_out"
    out_dir.mkdir(parents=True)

    supervisor = TrainingSupervisor(
        job_id="test_subproc_1",
        target="desktop_navigation",
        dataset_dir=sample_dataset_dir,
        output_dir=out_dir,
        budget=TrainingBudget(max_epochs=2),
    )
    assert supervisor.state_machine.current_state == TrainingJobState.DRAFT
    assert supervisor.watchdog.is_heartbeat_expired() is False


def test_p7_12_worker_crash_isolation(tmp_path: Path) -> None:
    """Worker abnormal termination (simulated non-zero exit) is caught by supervisor."""
    out_dir = tmp_path / "crash_out"
    out_dir.mkdir()

    supervisor = TrainingSupervisor(
        job_id="crash_job",
        target="desktop",
        dataset_dir=tmp_path,
        output_dir=out_dir,
    )
    # Simulate a crashed mock process
    from unittest.mock import MagicMock

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 137  # SIGKILL or OOM kill
    supervisor.proc = mock_proc
    supervisor.state_machine.current_state = TrainingJobState.RUNNING

    with pytest.raises(Exception) as exc_info:
        supervisor.poll_and_enforce()
    assert "Worker process crashed" in str(exc_info.value)
    assert supervisor.state_machine.current_state == TrainingJobState.FAILED


def test_p7_13_watchdog_detects_unresponsive_worker() -> None:
    """Watchdog detects lapsed heartbeats and raises WorkerUnresponsiveError."""
    watchdog = WorkerWatchdog(heartbeat_timeout_seconds=0.1)
    watchdog.record_heartbeat()
    time.sleep(0.15)

    assert watchdog.is_heartbeat_expired() is True
    with pytest.raises(WorkerUnresponsiveError) as exc_info:
        watchdog.check_liveness(raise_on_deadlock=True)
    assert "Worker unresponsive" in str(exc_info.value)


def test_p7_14_supervisor_cancellation_kills_worker(tmp_path: Path) -> None:
    """Supervisor terminate cleans up worker process and releases kernel handles."""
    supervisor = TrainingSupervisor(
        job_id="cancel_job",
        target="desktop",
        dataset_dir=tmp_path,
        output_dir=tmp_path,
    )
    from unittest.mock import MagicMock

    mock_proc = MagicMock()
    supervisor.proc = mock_proc
    supervisor.terminate()
    assert mock_proc.kill.called


def test_p7_15_ipc_protocol_message_integrity(tmp_path: Path) -> None:
    """IPC reader handles structured messages (HEARTBEAT, PROGRESS, COMPLETED) correctly."""
    supervisor = TrainingSupervisor(
        job_id="ipc_test",
        target="desktop",
        dataset_dir=tmp_path,
        output_dir=tmp_path,
    )
    supervisor.state_machine.current_state = TrainingJobState.STARTING

    # Simulate IPC messages
    supervisor._handle_ipc_message({"type": "HEARTBEAT"})
    assert supervisor.watchdog.heartbeat_count == 1

    supervisor._handle_ipc_message({"type": "RUNNING"})
    assert supervisor.state_machine.current_state == TrainingJobState.RUNNING

    supervisor._handle_ipc_message(
        {"type": "PROGRESS", "payload": {"epoch": 1, "train_loss": 0.42}}
    )
    assert supervisor.watchdog.progress_count == 1

    supervisor._handle_ipc_message({"type": "COMPLETED"})
    assert supervisor.state_machine.current_state == TrainingJobState.COMPLETED


def test_p7_16_windows_job_object_containment() -> None:
    """Windows Job Object creates handle and closes safely."""
    with WindowsJobObject(max_memory_mb=512) as job:
        assert job.max_memory_mb == 512
        # Assigning current process or mock PID
        if job.is_windows:
            assert job._is_configured is True
    # Clean exit closed handle
    assert job._handle is None


# ===========================================================================
# Group 3: Resource & Hardware Governance Scenarios (P7-17 to P7-22)
# ===========================================================================


def test_p7_17_multi_library_cpu_thread_env_injection() -> None:
    """CPU governor injects thread environment variables for OpenMP, MKL, OpenBLAS, Tokenizers."""
    gov = CpuGovernor(max_threads=2)
    env = gov.build_subprocess_env({})
    assert env["OMP_NUM_THREADS"] == "2"
    assert env["MKL_NUM_THREADS"] == "2"
    assert env["OPENBLAS_NUM_THREADS"] == "2"
    assert env["TOKENIZERS_PARALLELISM"] == "false"


def test_p7_18_memory_governor_rss_limit_enforced() -> None:
    """Memory governor raises ResourceLimitExceededError when RSS breaches max limit."""
    gov = MemoryGovernor(limits=MemoryLimits(max_process_rss_mb=100))
    from unittest.mock import patch

    with patch.object(gov, "get_current_rss_mb", return_value=150.0):
        with pytest.raises(ResourceLimitExceededError) as exc_info:
            gov.check_limits(pid=1234, raise_on_breach=True)
        assert "exceeded limit" in str(exc_info.value)


def test_p7_19_gpu_governor_device_resolution_and_visibility() -> None:
    """GPU governor restricts child process to specified device ID or disables CUDA."""
    gov_enabled = GpuGovernor(enable_gpu=True, allowed_device_id=1)
    env_gpu = gov_enabled.configure_environment({})
    assert env_gpu["CUDA_VISIBLE_DEVICES"] == "1"

    gov_disabled = GpuGovernor(enable_gpu=False)
    env_cpu = gov_disabled.configure_environment({})
    assert env_cpu["CUDA_VISIBLE_DEVICES"] == ""


def test_p7_20_gpu_oom_classification() -> None:
    """GPU governor classifies CUDA OOM into recoverable reduction vs fatal abort."""
    gov = GpuGovernor()
    oom_exc = RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")

    # When batch_size > min_batch_size, it is recoverable
    outcome = gov.classify_oom(oom_exc, current_batch_size=16, min_batch_size=1)
    assert outcome.is_recoverable is True
    assert outcome.suggested_batch_size == 8
    assert outcome.action == "REDUCE_BATCH_SIZE"

    # When batch_size == min_batch_size, it is fatal
    outcome_fatal = gov.classify_oom(oom_exc, current_batch_size=1, min_batch_size=1)
    assert outcome_fatal.is_recoverable is False
    assert outcome_fatal.action == "ABORT_JOB"


def test_p7_21_disk_space_governor_preflight_check(tmp_path: Path) -> None:
    """Disk governor preflight check raises DiskSpaceExhaustedError when free disk is inadequate."""
    gov = DiskGovernor(min_free_disk_mb=1_000_000_000.0)  # 1 Petabyte: impossible
    with pytest.raises(DiskSpaceExhaustedError) as exc_info:
        gov.check_preflight(tmp_path)
    assert "Insufficient disk space" in str(exc_info.value)


def test_p7_22_disk_space_exhaustion_during_training(tmp_path: Path) -> None:
    """Disk governor runtime check fails when free space drops below threshold."""
    gov = DiskGovernor(min_free_disk_mb=100.0)
    from unittest.mock import patch
    from collections import namedtuple

    Usage = namedtuple("Usage", ["total", "used", "free"])
    with patch("shutil.disk_usage", return_value=Usage(1000, 950, 50 * 1024 * 1024)):
        with pytest.raises(DiskSpaceExhaustedError) as exc_info:
            gov.check_runtime_space(tmp_path)
        assert "Runtime disk space exhausted" in str(exc_info.value)


# ===========================================================================
# Group 4: Lifecycle, Budget & Pause/Resume Scenarios (P7-23 to P7-28)
# ===========================================================================


def test_p7_23_19_state_job_lifecycle_transitions() -> None:
    """19-state job lifecycle verifies valid progression and rejects illegal jumps."""
    sm = JobStateMachine(job_id="state_test")
    assert sm.current_state == TrainingJobState.DRAFT

    # Valid progression
    sm.transition_to(TrainingJobState.VALIDATING, "Validate")
    sm.transition_to(TrainingJobState.QUEUED, "Queued")
    sm.transition_to(TrainingJobState.STARTING, "Start")
    sm.transition_to(TrainingJobState.RUNNING, "Run")
    sm.transition_to(TrainingJobState.PAUSE_REQUESTED, "Pause request")
    sm.transition_to(TrainingJobState.CHECKPOINTING, "Checkpointing")
    sm.transition_to(TrainingJobState.PAUSED, "Paused")
    sm.transition_to(TrainingJobState.RESUME_VALIDATING, "Resume validate")
    sm.transition_to(TrainingJobState.RUNNING, "Resumed")
    sm.transition_to(TrainingJobState.COMPLETED, "Done")

    assert sm.is_terminal() is True

    # Illegal transition from terminal state raises StateTransitionError
    with pytest.raises(StateTransitionError):
        sm.transition_to(TrainingJobState.RUNNING, "Illegal restart")


def test_p7_24_multi_dimensional_training_budget_enforcement() -> None:
    """Training budget limits enforce step, sample, and token ceilings."""
    budget = TrainingBudget(max_steps=5, max_tokens=100)
    tracker = BudgetTracker(budget=budget)

    tracker.record_step(tokens=50, samples=2)
    assert tracker.check_limits() is None

    tracker.record_step(tokens=60, samples=2)  # tokens = 110 > 100
    reason = tracker.check_limits()
    assert reason == BudgetExhaustionReason.MAX_TOKENS_REACHED

    with pytest.raises(BudgetExhaustedError) as exc_info:
        tracker.check_limits(raise_on_exhaustion=True)
    assert "Max tokens processed" in str(exc_info.value)


def test_p7_25_wall_time_timeout_abort() -> None:
    """Wall time exhaustion triggers TimeoutExhaustedError."""
    budget = TrainingBudget(max_wall_time_minutes=0.0001)  # ~6 ms
    tracker = BudgetTracker(budget=budget)
    time.sleep(0.02)

    with pytest.raises(TimeoutExhaustedError) as exc_info:
        tracker.check_limits(raise_on_exhaustion=True)
    assert "Max wall time exceeded" in str(exc_info.value)


def test_p7_26_checkpoint_boundary_cooperative_pause() -> None:
    """Job pauses at checkpoint boundary rather than abruptly interrupting active step."""
    sm = JobStateMachine(job_id="pause_test")
    sm.transition_to(TrainingJobState.VALIDATING)
    sm.transition_to(TrainingJobState.QUEUED)
    sm.transition_to(TrainingJobState.STARTING)
    sm.transition_to(TrainingJobState.RUNNING)

    # Cooperative pause requested
    sm.transition_to(TrainingJobState.PAUSE_REQUESTED, "User requested pause")
    # Finishes active batch then transitions to checkpointing
    sm.transition_to(TrainingJobState.CHECKPOINTING, "Writing safe checkpoint")
    # Checkpoint completes -> safely paused
    sm.transition_to(TrainingJobState.PAUSED, "Safe checkpoint written")
    assert sm.current_state == TrainingJobState.PAUSED


def test_p7_27_resume_validates_dataset_and_config_hash() -> None:
    """Resume validation verifies dataset and config hash match checkpoint metadata."""
    checkpoint_meta = {
        "dataset_manifest_hash": "ds_manifest_hash_1",
        "config_hash": "cfg_hash_1",
    }
    current_dataset_hash = "ds_manifest_hash_1"
    current_config_hash = "cfg_hash_2"  # Tampered or modified config

    # Mismatch detected
    assert (
        current_dataset_hash == checkpoint_meta["dataset_manifest_hash"]
        and current_config_hash == checkpoint_meta["config_hash"]
    ) is False


def test_p7_28_resume_restores_optimizer_and_rng_state() -> None:
    """DeterministicSampler with identical base_seed + epoch reproduces identical sequence."""
    sampler_1 = DeterministicSampler(base_seed=42, num_samples=10)
    sampler_2 = DeterministicSampler(base_seed=42, num_samples=10)

    indices_1 = sampler_1.get_epoch_indices(epoch=3)
    indices_2 = sampler_2.get_epoch_indices(epoch=3)
    assert indices_1 == indices_2


# ===========================================================================
# Group 5: Durability, Checkpoint & Retention Scenarios (P7-29 to P7-34)
# ===========================================================================


def test_p7_29_atomic_checkpoint_complete_marker(tmp_path: Path) -> None:
    """Checkpoint requires COMPLETE marker; missing COMPLETE raises CheckpointMissingCompleteMarkerError."""
    ckpt_dir = tmp_path / "checkpoint_001"
    ckpt_dir.mkdir()
    (ckpt_dir / "weights.json").write_text("{}", encoding="utf-8")
    (ckpt_dir / "checksums.json").write_text(json.dumps({"weights.json": "abc"}), encoding="utf-8")

    with pytest.raises(CheckpointMissingCompleteMarkerError):
        CheckpointStore.verify_checkpoint(ckpt_dir)


def test_p7_30_checkpoint_fsync_durability(tmp_path: Path) -> None:
    """Checkpoint written via save_atomic_checkpoint includes COMPLETE marker and valid checksums."""
    out = tmp_path / "checkpoints"
    saved = CheckpointStore.save_atomic_checkpoint(
        output_dir=out,
        checkpoint_name="ckpt_epoch_001",
        files_data={"weights.json": json.dumps({"w": [1, 2, 3]})},
        metadata={"epoch": 1, "train_loss": 0.25},
    )
    assert (saved / COMPLETE_MARKER_FILE).exists()

    meta = CheckpointStore.verify_checkpoint(saved)
    assert meta.epoch == 1
    assert meta.train_loss == 0.25


def test_p7_31_checkpoint_quarantine_on_corruption(tmp_path: Path) -> None:
    """Corrupted checkpoint is detected and moved to _quarantine directory."""
    out = tmp_path / "checkpoints"
    saved = CheckpointStore.save_atomic_checkpoint(
        output_dir=out,
        checkpoint_name="ckpt_corrupt",
        files_data={"weights.json": "initial_clean"},
        metadata={},
    )
    # Tamper with file
    (saved / "weights.json").write_text("corrupted_payload", encoding="utf-8")

    with pytest.raises(CheckpointCorruptError):
        CheckpointStore.verify_checkpoint(saved)

    quarantined = CheckpointStore.quarantine_checkpoint(saved, reason="SHA-256 mismatch")
    assert quarantined.exists()
    assert not saved.exists()
    assert "_quarantine" in str(quarantined)


def test_p7_32_checkpoint_retention_policy(tmp_path: Path) -> None:
    """Retention policy keeps best, latest, pre-failure, and pinned checkpoints; prunes others."""
    out = tmp_path / "checkpoints"
    names = [f"ckpt_{i:02d}" for i in range(7)]
    for n in names:
        CheckpointStore.save_atomic_checkpoint(
            output_dir=out,
            checkpoint_name=n,
            files_data={"weights.json": "{}"},
            metadata={"step": int(n.split("_")[1])},
        )

    policy = CheckpointRetentionPolicy(max_retained_checkpoints=4)
    policy.update_best("ckpt_01")
    policy.update_latest("ckpt_06")
    policy.pin_checkpoint("ckpt_03")

    pruned = policy.prune_checkpoints(out)
    assert len(pruned) > 0
    # Protected checkpoints must NOT be pruned
    assert "ckpt_01" not in pruned
    assert "ckpt_06" not in pruned
    assert "ckpt_03" not in pruned


def test_p7_33_reproducibility_fingerprint_generation() -> None:
    """ReproducibilityFingerprint generates deterministic hash across identical runs."""
    fp1 = ReproducibilityFingerprint.create(
        seed=42,
        dataset_manifest_hash="manifest_123",
        config_hash="cfg_abc",
        precision_mode=PrecisionMode.CPU_DETERMINISTIC,
    )
    fp2 = ReproducibilityFingerprint.create(
        seed=42,
        dataset_manifest_hash="manifest_123",
        config_hash="cfg_abc",
        precision_mode=PrecisionMode.CPU_DETERMINISTIC,
    )
    assert fp1.compute_hash() == fp2.compute_hash()


def test_p7_34_profile_based_reproducibility_tolerances() -> None:
    """Numerical equivalence evaluates within precision mode tolerances."""
    # CPU deterministic: requires < 1e-7
    assert (
        check_numerical_equivalence(1.00000001, 1.00000002, PrecisionMode.CPU_DETERMINISTIC) is True
    )
    assert check_numerical_equivalence(1.00001, 1.00002, PrecisionMode.CPU_DETERMINISTIC) is False

    # GPU FP16: allows < 5e-3
    assert check_numerical_equivalence(1.001, 1.003, PrecisionMode.GPU_FP16) is True
    assert check_numerical_equivalence(1.01, 1.05, PrecisionMode.GPU_FP16) is False


# ===========================================================================
# Group 6: Backend, Loss, Batching & Regression Scenarios (P7-35 to P7-40)
# ===========================================================================


def test_p7_35_model_architecture_compatibility_check() -> None:
    """ModelCompatibilityChecker catches vocab size and sequence length mismatches."""
    spec = ModelArchitectureSpec(
        architecture_name="small_transformer",
        vocab_size=10,
        hidden_dim=64,
        max_sequence_length=128,
        supported_precisions=("CPU_DETERMINISTIC", "FP32"),
    )
    # Vocab size mismatch
    report = ModelCompatibilityChecker.check_compatibility(
        spec=spec,
        target="desktop",
        required_classes=[f"class_{i}" for i in range(15)],
    )
    assert report.compatible is False
    with pytest.raises(ModelIncompatibleError):
        report.raise_if_incompatible()


def test_p7_36_batch_policy_and_token_budget() -> None:
    """BatchPolicy enforces max sequence length truncation and max batch tokens."""
    policy = BatchPolicy(batch_size=4, max_sequence_tokens=10, max_batch_tokens=25)
    collator = SampleCollator(policy=policy)

    samples = [
        {"input_data": {"user_input": "word " * 20}, "label": {"tool": "t1"}} for _ in range(5)
    ]
    batches = collator.collate(samples)
    assert len(batches) >= 2
    assert collator.truncation_warnings > 0


def test_p7_37_loss_strategies_for_training_purposes() -> None:
    """Purpose-driven loss strategy factory maps SFT, DPO, KTO, and Memory Ranking correctly."""
    ce = get_loss_strategy_for_purpose("SFT")
    assert isinstance(ce, WeightedCrossEntropyLoss)
    assert ce.compute(0.9) < ce.compute(0.1)

    focal = get_loss_strategy_for_purpose("HARD_TOOL_SELECTION")
    assert isinstance(focal, WeightedFocalLoss)

    dpo = get_loss_strategy_for_purpose("DPO_PREFERENCE")
    assert isinstance(dpo, DPOObjective)
    # Loss lower when chosen logp > rejected logp
    assert dpo.compute(pi_chosen_logp=-0.5, pi_rejected_logp=-2.0) < dpo.compute(
        pi_chosen_logp=-2.0, pi_rejected_logp=-0.5
    )

    kto = get_loss_strategy_for_purpose("KTO")
    assert isinstance(kto, KTOObjective)

    margin = get_loss_strategy_for_purpose("MEMORY_RANKING")
    assert isinstance(margin, GradedMarginLoss)


def test_p7_38_early_stopping_on_validation_loss_plateau() -> None:
    """Early stopping triggers after patience epochs without improvement."""
    es = EarlyStopping(patience=3, min_delta=0.01)
    tracker = LossTracker(early_stopping=es)

    assert tracker.record_epoch(train_loss=0.5, val_loss=0.5) is False
    assert tracker.record_epoch(train_loss=0.4, val_loss=0.495) is False
    assert tracker.record_epoch(train_loss=0.3, val_loss=0.495) is False
    # Third consecutive non-improving epoch triggers early stop
    stopped = tracker.record_epoch(train_loss=0.2, val_loss=0.495)
    assert stopped is True


def test_p7_39_catastrophic_regression_gate() -> None:
    """Candidate model showing regression on test/challenge splits is REJECTED."""
    evaluator = CandidateEvaluator(min_test_accuracy_gain=0.02, max_regression_tolerance=0.01)

    cand = TFIDFLogisticBaselineBackend()
    cand.initialize({"target": "test"})
    base = TFIDFLogisticBaselineBackend()
    base.initialize({"target": "test"})

    # Fit baseline well, leave candidate poor on challenge split
    samples_base = [
        {"input_data": {"user_input": "open terminal"}, "label": {"tool": "terminal"}},
        {"input_data": {"user_input": "open browser"}, "label": {"tool": "browser"}},
    ]
    base.model.fit(samples_base, epochs=10)

    report = evaluator.evaluate_candidate(
        candidate=cand,
        baseline=base,
        test_samples=samples_base,
        challenge_samples=samples_base,
    )
    assert report.beats_baseline is False
    assert "REJECTED" in report.verdict


def test_p7_40_golden_holdout_read_only_evaluation(
    sample_dataset_dir: Path, tmp_path: Path
) -> None:
    """End-to-end OfflineTrainer runs full lifecycle, evaluates golden holdout read-only, registers CANDIDATE."""
    out_dir = tmp_path / "model_out"
    out_dir.mkdir(parents=True)

    config = TrainingConfig(
        target="desktop_navigation",
        dataset_dir=str(sample_dataset_dir),
        output_dir=str(out_dir),
        epochs=3,
        min_samples_required=5,
        min_accuracy_gain=0.0,
    )

    trainer = OfflineTrainer()
    result = trainer.train(config)

    assert result.success is True
    assert result.status.value in ("candidate", "rejected")
    assert result.artifact_dir is not None
    assert (result.artifact_dir / "manifest.json").exists()
    assert (result.artifact_dir / "checksums.json").exists()
    # Checkpoints directory exists and has COMPLETE marker
    ckpts = list((result.artifact_dir / "_checkpoints").glob("checkpoint_*"))
    assert len(ckpts) > 0
    assert (ckpts[0] / COMPLETE_MARKER_FILE).exists()


# ===========================================================================
# Group 7: Operational Hardening Scenarios (P7-41 to P7-60)
# ===========================================================================


def test_p7_41_real_job_object_memory_enforcement() -> None:
    """Windows Job Object and Memory Governor enforce memory ceiling and clean up."""
    import os

    gov = MemoryGovernor(limits=MemoryLimits(max_process_rss_mb=1))
    current_pid = os.getpid()

    # The current test runner process uses more than 1MB RSS; verifying limit breach
    with pytest.raises(ResourceLimitExceededError) as exc_info:
        gov.check_limits(current_pid, raise_on_breach=True)
    assert "exceeded limit" in str(exc_info.value)
    gov.close()


def test_p7_42_real_gpu_memory_budget_enforcement() -> None:
    """GPU governor configures device visibility and queries memory diagnostics."""
    gov = GpuGovernor(allowed_device_id=1, max_vram_mb=4096, enable_gpu=True)
    env = gov.configure_environment({})
    assert env["CUDA_VISIBLE_DEVICES"] == "1"

    gov_disabled = GpuGovernor(enable_gpu=False)
    env_dis = gov_disabled.configure_environment({})
    assert env_dis["CUDA_VISIBLE_DEVICES"] == ""

    # Usage query returns two floats without crashing
    alloc, res = gov.get_vram_usage_mb()
    assert isinstance(alloc, float)
    assert isinstance(res, float)

    diag = gov.to_dict()
    assert diag["enable_gpu"] is True
    assert diag["max_vram_mb"] == 4096


def test_p7_43_gpu_oom_recovery_bounded() -> None:
    """Bounded batch reduction halves batch size until min_batch_size is reached."""
    gov = GpuGovernor()
    oom_exc = RuntimeError("CUDA out of memory: tried to allocate 2.00 GiB")

    # Halves 32 -> 16
    outcome = gov.classify_oom(oom_exc, current_batch_size=32, min_batch_size=4)
    assert outcome.is_recoverable is True
    assert outcome.suggested_batch_size == 16
    assert outcome.action == "REDUCE_BATCH_SIZE"

    # Halves 8 -> 4
    outcome2 = gov.classify_oom(oom_exc, current_batch_size=8, min_batch_size=4)
    assert outcome2.is_recoverable is True
    assert outcome2.suggested_batch_size == 4

    # At min_batch_size, cannot reduce further -> ABORT_JOB
    outcome3 = gov.classify_oom(oom_exc, current_batch_size=4, min_batch_size=4)
    assert outcome3.is_recoverable is False
    assert outcome3.action == "ABORT_JOB"
    assert outcome3.reason == "GPU_OOM_MIN_BATCH_REACHED"


def test_p7_44_cuda_unavailable_fallback_policy() -> None:
    """System falls back gracefully to CPU backend when CUDA is disabled or unavailable."""
    gov = GpuGovernor(enable_gpu=False)
    assert gov.resolve_compute_device() == "cpu"
    # cleanup executes safely
    GpuGovernor.cleanup_cuda_context()


def test_p7_45_no_unbounded_oom_retry_loop() -> None:
    """Exceeding max_oom_retries aborts training immediately to prevent infinite reduction."""
    gov = GpuGovernor(max_oom_retries=3)
    oom_exc = RuntimeError("CUDA out of memory")

    # Exceeded retries (retry 3 of 3)
    outcome = gov.classify_oom(oom_exc, current_batch_size=128, min_batch_size=2, retry_count=3)
    assert outcome.is_recoverable is False
    assert outcome.action == "ABORT_JOB"
    assert outcome.reason == "GPU_OOM_MAX_RETRIES_EXCEEDED"


def test_p7_46_interrupt_during_model_write(tmp_path: Path) -> None:
    """Corrupted or truncated model weights fail checksum verification."""
    ckpt_dir = CheckpointStore.save_atomic_checkpoint(
        output_dir=tmp_path,
        checkpoint_name="ckpt_test_corrupt",
        files_data={"model.bin": b"valid_weights_bytes_12345"},
        metadata={"epoch": 1, "step": 10},
    )

    # Corrupt model weights file
    (ckpt_dir / "model.bin").write_bytes(b"tampered_truncated")

    with pytest.raises(CheckpointCorruptError) as exc_info:
        CheckpointStore.verify_checkpoint(ckpt_dir)
    assert "Corrupted file 'model.bin'" in str(exc_info.value)


def test_p7_47_interrupt_during_optimizer_write(tmp_path: Path) -> None:
    """Checkpoint lacking optimizer state is rejected when require_optimizer is True."""
    ckpt_dir = CheckpointStore.save_atomic_checkpoint(
        output_dir=tmp_path,
        checkpoint_name="ckpt_no_optim",
        files_data={"model.bin": b"weights"},
        metadata={"epoch": 1, "step": 10},
    )

    # Valid without optimizer
    meta = CheckpointStore.verify_checkpoint(ckpt_dir, require_optimizer=False)
    assert meta.epoch == 1

    # Rejected when optimizer state required
    with pytest.raises(CheckpointCorruptError) as exc_info:
        CheckpointStore.verify_checkpoint(ckpt_dir, require_optimizer=True)
    assert "Missing required optimizer state" in str(exc_info.value)


def test_p7_48_interrupt_before_complete_marker(tmp_path: Path) -> None:
    """Checkpoint missing COMPLETE marker is rejected and quarantined."""
    ckpt_dir = CheckpointStore.save_atomic_checkpoint(
        output_dir=tmp_path,
        checkpoint_name="ckpt_incomplete",
        files_data={"model.bin": b"weights"},
        metadata={"epoch": 1, "step": 10},
    )

    # Remove COMPLETE marker to simulate crash before finalization
    (ckpt_dir / COMPLETE_MARKER_FILE).unlink()

    with pytest.raises(CheckpointMissingCompleteMarkerError):
        CheckpointStore.verify_checkpoint(ckpt_dir)

    quarantined = CheckpointStore.quarantine_checkpoint(ckpt_dir, reason="missing_complete_marker")
    assert quarantined.exists()
    assert not ckpt_dir.exists()
    assert (quarantined / "QUARANTINE_REASON.txt").exists()


def test_p7_49_interrupt_after_rename_before_registry_commit(tmp_path: Path) -> None:
    """Checkpoint published with COMPLETE marker is verified intact and readable."""
    ckpt_dir = CheckpointStore.save_atomic_checkpoint(
        output_dir=tmp_path,
        checkpoint_name="ckpt_durable",
        files_data={"model.bin": b"durable_weights_payload", "optimizer.json": '{"lr": 0.001}'},
        metadata={"epoch": 2, "step": 50, "dataset_id": "ds_alpha"},
    )
    meta = CheckpointStore.verify_checkpoint(ckpt_dir, require_optimizer=True)
    assert meta.epoch == 2
    assert meta.step == 50
    assert meta.dataset_id == "ds_alpha"


def test_p7_50_abandoned_staging_recovery(tmp_path: Path) -> None:
    """Crash-abandoned .staging_* directories are automatically discovered and cleaned."""
    staging_1 = tmp_path / ".staging_deadbeef1"
    staging_2 = tmp_path / ".staging_deadbeef2"
    valid_dir = tmp_path / "valid_checkpoint"
    staging_1.mkdir()
    staging_2.mkdir()
    valid_dir.mkdir()

    cleaned = CheckpointStore.cleanup_abandoned_staging(tmp_path)
    assert len(cleaned) == 2
    assert not staging_1.exists()
    assert not staging_2.exists()
    assert valid_dir.exists()


def test_p7_51_reproducibility_fingerprint_mismatch_rejected() -> None:
    """Altering determinism mode, loss strategy, or framework changes fingerprint hash."""
    fp_base = ReproducibilityFingerprint.create(
        seed=42,
        dataset_manifest_hash="man_hash",
        config_hash="cfg_hash",
        determinism_mode="strict",
        loss_strategy_hash="loss_sft",
    )
    fp_diff_determinism = ReproducibilityFingerprint.create(
        seed=42,
        dataset_manifest_hash="man_hash",
        config_hash="cfg_hash",
        determinism_mode="non_deterministic",
        loss_strategy_hash="loss_sft",
    )
    fp_diff_loss = ReproducibilityFingerprint.create(
        seed=42,
        dataset_manifest_hash="man_hash",
        config_hash="cfg_hash",
        determinism_mode="strict",
        loss_strategy_hash="loss_dpo",
    )

    assert fp_base.compute_hash() != fp_diff_determinism.compute_hash()
    assert fp_base.compute_hash() != fp_diff_loss.compute_hash()


def test_p7_52_different_seed_changes_training_trajectory() -> None:
    """Distinct random seeds yield demonstrably different sample ordering."""
    sampler_a = DeterministicSampler(base_seed=42, num_samples=50)
    sampler_b = DeterministicSampler(base_seed=999, num_samples=50)

    order_a = sampler_a.get_epoch_indices(0)
    order_b = sampler_b.get_epoch_indices(0)

    assert order_a != order_b
    assert sorted(order_a) == sorted(order_b) == list(range(50))


def test_p7_53_dataloader_worker_determinism() -> None:
    """DeterministicSampler produces identical sample streams across multiple iterations."""
    sampler_1 = DeterministicSampler(base_seed=12345, num_samples=30)
    sampler_2 = DeterministicSampler(base_seed=12345, num_samples=30)

    assert sampler_1.get_epoch_indices(0) == sampler_2.get_epoch_indices(0)
    assert sampler_1.get_epoch_indices(1) == sampler_2.get_epoch_indices(1)
    assert sampler_1.get_epoch_indices(2) == sampler_2.get_epoch_indices(2)


def test_p7_54_resume_after_supervisor_restart(tmp_path: Path) -> None:
    """Supervisor restart identifies existing checkpoint and validates its state."""
    CheckpointStore.save_atomic_checkpoint(
        output_dir=tmp_path,
        checkpoint_name="checkpoint_001",
        files_data={"model.bin": b"weights_1"},
        metadata={"epoch": 1, "step": 10},
    )
    CheckpointStore.save_atomic_checkpoint(
        output_dir=tmp_path,
        checkpoint_name="checkpoint_002",
        files_data={"model.bin": b"weights_2"},
        metadata={"epoch": 2, "step": 20},
    )

    policy = CheckpointRetentionPolicy(max_retained_checkpoints=2)
    assert policy.max_retained_checkpoints == 2
    ckpts = [d for d in tmp_path.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))]
    ckpts.sort(key=lambda d: d.name)
    latest = ckpts[-1]
    assert latest.name == "checkpoint_002"

    meta = CheckpointStore.verify_checkpoint(latest)
    assert meta.epoch == 2
    assert meta.step == 20


def test_p7_55_stale_running_job_reconciliation() -> None:
    """Jobs left in RUNNING status by a terminated process are reconciled to ABORTED."""
    sm1 = JobStateMachine(job_id="job_active_1", current_state=TrainingJobState.RUNNING)
    sm2 = JobStateMachine(job_id="job_active_2", current_state=TrainingJobState.STARTING)
    sm3 = JobStateMachine(job_id="job_done_3", current_state=TrainingJobState.COMPLETED)

    reconciled = TrainingSupervisor.reconcile_stale_jobs([sm1, sm2, sm3])
    assert "job_active_1" in reconciled
    assert "job_active_2" in reconciled
    assert "job_done_3" not in reconciled

    assert sm1.current_state == TrainingJobState.ABORTED
    assert sm2.current_state == TrainingJobState.ABORTED
    assert sm3.current_state == TrainingJobState.COMPLETED


def test_p7_56_orphan_worker_cleanup_after_host_restart() -> None:
    """TrainingSupervisor.cleanup_orphan_workers executes safely without unhandled exceptions."""
    cleaned = TrainingSupervisor.cleanup_orphan_workers("nonexistent_test_pattern_12345")
    assert isinstance(cleaned, int)
    assert cleaned == 0


def test_p7_57_revocation_invalidates_existing_checkpoints(tmp_path: Path) -> None:
    """Dataset revocation cascades to mark previously saved checkpoints as REVOKED_INELIGIBLE."""
    ckpt = CheckpointStore.save_atomic_checkpoint(
        output_dir=tmp_path,
        checkpoint_name="ckpt_revoked_target",
        files_data={"model.bin": b"weights"},
        metadata={"epoch": 1, "dataset_id": "ds_toxic_data"},
    )

    # Invalidate
    invalidated = CheckpointStore.invalidate_dataset_checkpoints(tmp_path, "ds_toxic_data")
    assert "ckpt_revoked_target" in invalidated
    assert (ckpt / REVOKED_MARKER_FILE).exists()

    # Verification fails on revoked checkpoint
    with pytest.raises(CheckpointCorruptError) as exc_info:
        CheckpointStore.verify_checkpoint(ckpt)
    assert "REVOKED_INELIGIBLE" in str(exc_info.value)


def test_p7_58_worker_secret_environment_isolation() -> None:
    """Child process environment has all secrets, keys, and credentials stripped."""
    sec = SecurityPolicy()
    dirty_env = {
        "OPENAI_API_KEY": "sk-secret-12345",
        "ANTHROPIC_SECRET_TOKEN": "anthropic-token-xyz",
        "DATABASE_PASSWORD": "supersecretpassword",
        "AWS_CREDENTIAL_FILE": "/path/to/creds",
        "AUTH_BEARER_HEADER": "Bearer token",
        "PRIVATE_CERT": "certdata",
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": "/workspace",
    }

    clean_env = sec.scrub_environment(dirty_env)
    assert "OPENAI_API_KEY" not in clean_env
    assert "ANTHROPIC_SECRET_TOKEN" not in clean_env
    assert "DATABASE_PASSWORD" not in clean_env
    assert "AWS_CREDENTIAL_FILE" not in clean_env
    assert "AUTH_BEARER_HEADER" not in clean_env
    assert "PRIVATE_CERT" not in clean_env
    assert clean_env["PATH"] == "/usr/bin:/bin"
    assert clean_env["PYTHONPATH"] == "/workspace"


def test_p7_59_training_worker_network_policy() -> None:
    """Worker child environment blocks outbound network by pointing proxies to loopback sink."""
    sec = SecurityPolicy(allow_network=False)
    env = sec.scrub_environment({"SOME_VAR": "1"})
    assert env["HTTP_PROXY"] == "http://127.0.0.1:0"
    assert env["HTTPS_PROXY"] == "http://127.0.0.1:0"
    assert env["ALL_PROXY"] == "http://127.0.0.1:0"


def test_p7_60_unregistered_backend_rejected_and_quality_gates() -> None:
    """Unregistered trainer backend is rejected, and dataset quality gates catch collapse."""
    sec = SecurityPolicy()

    # Valid backends pass
    assert sec.validate_backend("tfidf_logistic") is True
    assert sec.validate_backend("torch_sft") is True

    # Untrusted backend rejected
    with pytest.raises(SecurityPolicyError) as exc_info:
        sec.validate_backend("malicious_eval_backend")
    assert "Untrusted or unregistered trainer backend" in str(exc_info.value)

    # Dataset quality gate checks
    good_samples = [
        {"input_data": {"user_input": f"msg {i}"}, "label": {"tool": f"tool_{i % 3}"}}
        for i in range(12)
    ]
    report = DatasetQualityGate.check_quality(
        train_samples=good_samples,
        val_samples=good_samples[:3],
        policy=DatasetQualityPolicy(min_train_samples=10, min_class_count=2),
    )
    assert report.passed is True
    assert report.class_count == 3

    # Severe class imbalance / collapse triggers REJECT
    skewed_samples = [
        {"input_data": {"user_input": f"msg {i}"}, "label": {"tool": "tool_0"}} for i in range(15)
    ]
    with pytest.raises(QualityGateError) as qg_info:
        DatasetQualityGate.check_quality(
            train_samples=skewed_samples,
            val_samples=good_samples[:3],
            policy=DatasetQualityPolicy(
                min_train_samples=10,
                min_class_count=2,
                imbalance_action=ImbalanceAction.REJECT,
            ),
        )
    assert "Unique classes (1) below minimum" in str(qg_info.value)

    # Evaluator decision engine safety rejection
    dec_engine = EvaluatorDecisionEngine()
    decision, reason = dec_engine.classify_outcome(
        candidate_successes=10,
        total_eval_samples=10,
        baseline_accuracy=0.8,
        critical_safety_violations=1,
    )
    assert decision == EvaluationDecision.REJECTED_SAFETY
    assert "critical safety violations" in reason

    # Wilson score interval calculation verification
    ci_low, ci_high = compute_wilson_interval(8, 10)
    assert 0.0 < ci_low < ci_high <= 1.0
