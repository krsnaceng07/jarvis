"""jarvis_learning.training.errors — typed error taxonomy for training and governance.

Covers all 25+ failure modes across dataset validation, resource boundaries,
subprocess execution, checkpoint durability, and model compatibility.
"""

from __future__ import annotations


class TrainingError(Exception):
    """Base exception for all training pipeline and governance errors."""

    def __init__(self, message: str, code: str = "TRAINING_ERROR") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Governance & Dataset Verification Errors (Gates 1-6)
# ---------------------------------------------------------------------------


class DatasetUnapprovedError(TrainingError):
    """Raised when dataset is not approved for training or lacks operator approval."""

    def __init__(
        self,
        message: str = "Dataset is not approved for training",
        code: str = "UNAPPROVED_DATASET",
    ) -> None:
        super().__init__(message, code=code)


class DatasetUnfrozenError(TrainingError):
    """Raised when dataset is still mutable or not frozen."""

    def __init__(
        self, message: str = "Dataset must be in FROZEN state", code: str = "UNFROZEN_DATASET"
    ) -> None:
        super().__init__(message, code=code)


class DatasetRevokedError(TrainingError):
    """Raised when dataset is revoked before or during training execution."""

    def __init__(
        self, message: str = "Dataset has been revoked", code: str = "REVOKED_DATASET"
    ) -> None:
        super().__init__(message, code=code)


class ScopeMismatchError(TrainingError):
    """Raised when operator approval scope does not match the training target."""

    def __init__(
        self,
        message: str = "Operator approval scope does not match target",
        code: str = "SCOPE_MISMATCH",
    ) -> None:
        super().__init__(message, code=code)


class IntegrityMismatchError(TrainingError):
    """Raised when dataset manifest hash or Merkle tree root fails verification."""

    def __init__(
        self,
        message: str = "Dataset manifest hash or Merkle root mismatch",
        code: str = "INTEGRITY_MISMATCH",
    ) -> None:
        super().__init__(message, code=code)


class PartitionLeakageError(TrainingError):
    """Raised when evaluation partitions leak into training samples."""

    def __init__(
        self,
        message: str = "Partition leakage detected in training samples",
        code: str = "PARTITION_LEAKAGE",
    ) -> None:
        super().__init__(message, code=code)


class GoldenHoldoutViolationError(TrainingError):
    """Raised when golden holdout samples are loaded into training or used for tuning."""

    def __init__(
        self,
        message: str = "Golden holdout partition is sealed and evaluation-only",
        code: str = "GOLDEN_HOLDOUT_VIOLATION",
    ) -> None:
        super().__init__(message, code=code)


class ChallengePartitionLeakageError(TrainingError):
    """Raised when challenge partition samples leak into training."""

    def __init__(
        self,
        message: str = "Challenge partition samples found in training set",
        code: str = "CHALLENGE_PARTITION_LEAKAGE",
    ) -> None:
        super().__init__(message, code=code)


# ---------------------------------------------------------------------------
# Concurrency & Lock Errors
# ---------------------------------------------------------------------------


class ConcurrencyLimitError(TrainingError):
    """Raised when attempting to run multiple training jobs concurrently."""

    def __init__(
        self, message: str = "Concurrent training jobs are not permitted (limit=1)"
    ) -> None:
        super().__init__(message, code="CONCURRENCY_LIMIT_EXCEEDED")


class DatasetLockError(TrainingError):
    """Raised when dataset input lock cannot be acquired or is violated."""

    def __init__(self, message: str = "Failed to acquire or maintain dataset lock") -> None:
        super().__init__(message, code="DATASET_LOCK_ERROR")


# ---------------------------------------------------------------------------
# Subprocess & Worker Lifecycle Errors
# ---------------------------------------------------------------------------


class WorkerCrashError(TrainingError):
    """Raised when the training worker child process exits abnormally."""

    def __init__(self, message: str, exit_code: int | None = None) -> None:
        super().__init__(message, code="WORKER_CRASHED")
        self.exit_code = exit_code


class WorkerUnresponsiveError(TrainingError):
    """Raised when the training worker heartbeat times out (deadlock)."""

    def __init__(self, message: str = "Worker heartbeat timed out; process unresponsive") -> None:
        super().__init__(message, code="WORKER_UNRESPONSIVE")


class StateTransitionError(TrainingError):
    """Raised when an illegal job state transition is attempted."""

    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Invalid state transition from '{from_state}' to '{to_state}'",
            code="INVALID_STATE_TRANSITION",
        )
        self.from_state = from_state
        self.to_state = to_state


# ---------------------------------------------------------------------------
# Resource & Budget Errors
# ---------------------------------------------------------------------------


class ResourceLimitExceededError(TrainingError):
    """Raised when memory, CPU, or GPU resource limits are breached."""

    def __init__(self, message: str, resource_type: str = "generic") -> None:
        super().__init__(message, code="RESOURCE_LIMIT_EXCEEDED")
        self.resource_type = resource_type


class TimeoutExhaustedError(TrainingError):
    """Raised when wall-time budget is exhausted."""

    def __init__(self, message: str = "Training job exceeded maximum wall-time minutes") -> None:
        super().__init__(message, code="TIMEOUT_EXHAUSTED")


class DiskSpaceExhaustedError(TrainingError):
    """Raised when available disk space drops below safety threshold."""

    def __init__(self, message: str = "Disk space below minimum safety threshold") -> None:
        super().__init__(message, code="DISK_SPACE_EXHAUSTED")


class BudgetExhaustedError(TrainingError):
    """Raised when multi-dimensional training budget is exhausted."""

    def __init__(self, message: str, budget_dimension: str = "generic") -> None:
        super().__init__(message, code="BUDGET_EXHAUSTED")
        self.budget_dimension = budget_dimension


class GpuOOMError(TrainingError):
    """Raised on GPU Out-Of-Memory error with recoverable flag."""

    def __init__(self, message: str, is_recoverable: bool = False) -> None:
        super().__init__(message, code="GPU_OOM")
        self.is_recoverable = is_recoverable


# ---------------------------------------------------------------------------
# Checkpoint & Durability Errors
# ---------------------------------------------------------------------------


class CheckpointCorruptError(TrainingError):
    """Raised when checkpoint weights or checksums fail verification."""

    def __init__(
        self,
        message: str = "Checkpoint data or checksum is corrupted",
        code: str = "CHECKPOINT_CORRUPT",
    ) -> None:
        super().__init__(message, code=code)


class CheckpointMissingCompleteMarkerError(TrainingError):
    """Raised when a checkpoint directory lacks the COMPLETE marker file."""

    def __init__(
        self,
        message: str = "Checkpoint directory is missing COMPLETE marker",
        code: str = "CHECKPOINT_INCOMPLETE",
    ) -> None:
        super().__init__(message, code=code)


class CheckpointResumeError(TrainingError):
    """Raised when checkpoint cannot be resumed due to hash or state mismatch."""

    def __init__(
        self,
        message: str = "Cannot resume checkpoint: state or hash mismatch",
        code: str = "CHECKPOINT_RESUME_MISMATCH",
    ) -> None:
        super().__init__(message, code=code)


# ---------------------------------------------------------------------------
# Model Compatibility & Regression Errors
# ---------------------------------------------------------------------------


class ModelIncompatibleError(TrainingError):
    """Raised when model architecture, vocab, or adapter is incompatible."""

    def __init__(
        self,
        message: str = "Model architecture or adapter incompatible",
        code: str = "MODEL_INCOMPATIBLE",
    ) -> None:
        super().__init__(message, code=code)


class CatastrophicRegressionError(TrainingError):
    """Raised when candidate model regresses on benchmark, challenge, or test set."""

    def __init__(
        self,
        message: str = "Candidate model exhibited catastrophic regression",
        code: str = "CATASTROPHIC_REGRESSION",
    ) -> None:
        super().__init__(message, code=code)


class AutomaticDeploymentForbiddenError(TrainingError):
    """Raised when any code attempts to automatically deploy or activate a candidate model."""

    def __init__(
        self,
        message: str = "Automatic model deployment is strictly forbidden",
        code: str = "AUTOMATIC_DEPLOYMENT_FORBIDDEN",
    ) -> None:
        super().__init__(message, code=code)
