"""jarvis_learning.training — hardened offline training pipeline, resource governance, and supervision."""

from __future__ import annotations

from .backend_manifest import (
    CANONICAL_BACKENDS,
    BackendCapabilities,
    BackendManifest,
    get_backend_manifest,
    validate_preflight,
)
from .batching import BatchPolicy, DeterministicSampler, SampleCollator
from .budget import BudgetExhaustionReason, BudgetTracker, TrainingBudget
from .checkpoint_retention_policy import CheckpointRetentionPolicy
from .checkpoint_store import (
    CheckpointMetadata,
    CheckpointStore,
    CheckpointTransactionState,
)
from .comparison import BaselineComparator, ComparisonReport
from .confidence_intervals import (
    EvaluationDecision,
    EvaluatorDecisionEngine,
    compute_wilson_interval,
)
from .config import TrainingConfig
from .cpu_governor import CpuGovernor
from .dataset_lock import ConcurrencyController, TrainingInputLock
from .disk_governor import DiskGovernor
from .errors import (
    AutomaticDeploymentForbiddenError,
    BudgetExhaustedError,
    CatastrophicRegressionError,
    ChallengePartitionLeakageError,
    CheckpointCorruptError,
    CheckpointMissingCompleteMarkerError,
    CheckpointResumeError,
    ConcurrencyLimitError,
    DatasetLockError,
    DatasetRevokedError,
    DatasetUnapprovedError,
    DatasetUnfrozenError,
    DiskSpaceExhaustedError,
    GoldenHoldoutViolationError,
    GpuOOMError,
    IntegrityMismatchError,
    ModelIncompatibleError,
    PartitionLeakageError,
    ResourceLimitExceededError,
    ScopeMismatchError,
    StateTransitionError,
    TimeoutExhaustedError,
    TrainingError,
    WorkerCrashError,
    WorkerUnresponsiveError,
)
from .evaluation import (
    CandidateEvaluationReport,
    CandidateEvaluator,
    PartitionEvaluationResult,
)
from .governance import GovernanceCheckResult, TrainingGovernance
from .gpu_governor import (
    GpuFailureClass,
    GpuGovernor,
    GpuOomOutcome,
    classify_gpu_failure,
)
from .invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    INVARIANTS,
    InvariantEnforcementLevel,
    OperationalEvidenceLedger,
    OperationalInvariant,
    OperationalTestEvidence,
    TestExecutionClassification,
)
from .job_lifecycle import JobStateMachine, StateTransitionRecord, TrainingJobState
from .lease import (
    JobLease,
    JobLeaseHeldError,
    RecoveryState,
    SplitBrainDetectedError,
    SupervisorLeaseManager,
)
from .loss import (
    DPOObjective,
    GradedMarginLoss,
    KTOObjective,
    WeightedCrossEntropyLoss,
    WeightedFocalLoss,
    get_loss_strategy_for_purpose,
)
from .loss_tracker import EarlyStopping, LossTracker
from .memory_governor import MemoryGovernor, MemoryLimits
from .model_compatibility import (
    ModelArchitectureSpec,
    ModelCompatibilityChecker,
    ModelCompatibilityReport,
)
from .numerical_stability import (
    GradientExplosionError,
    InfLossError,
    LossStagnationError,
    NaNLossError,
    NonfiniteParameterError,
    NumericalFaultClass,
    NumericalPolicy,
    NumericalStabilityMonitor,
)
from .partition_guard import PartitionGuard, PartitionSampleManifest
from .quality_gates import (
    DatasetQualityGate,
    DatasetQualityPolicy,
    ImbalanceAction,
    QualityCheckReport,
    QualityGateError,
)
from .reproducibility import (
    ExecutionFingerprint,
    PrecisionMode,
    ReproducibilityFingerprint,
    ResumeCompatibilityFingerprint,
    RunIdentity,
    ToleranceProfile,
    check_numerical_equivalence,
)
from .resource_policy import TrainingExecutionController, TrainingResourcePolicy
from .revocation_graph import (
    ArtifactNode,
    ArtifactType,
    RevocationGraph,
    RevocationRecord,
)
from .security_policy import (
    ALLOWED_TRAINER_BACKENDS,
    SecurityPolicy,
    SecurityPolicyError,
)
from .supervisor import SupervisorOptions, TrainingSupervisor
from .trainer import OfflineTrainer, TrainResult
from .trainer_backend import (
    LoRATrainerBackend,
    TFIDFLogisticBaselineBackend,
    TorchPreferenceTrainerBackend,
    TorchSFTTrainerBackend,
    TrainerBackend,
    get_trainer_backend,
)
from .windows_job import WindowsJobObject
from .worker import TrainingWorkerChild
from .worker_identity import WorkerIdentityEnvelope, is_safe_to_reap

__all__ = [
    "ALLOWED_TRAINER_BACKENDS",
    "ArtifactNode",
    "ArtifactType",
    "AutomaticDeploymentForbiddenError",
    "BackendCapabilities",
    "BackendManifest",
    "BaselineComparator",
    "BatchPolicy",
    "BudgetExhaustionReason",
    "BudgetExhaustedError",
    "BudgetTracker",
    "CANONICAL_BACKENDS",
    "CandidateEvaluationReport",
    "CandidateEvaluator",
    "CatastrophicRegressionError",
    "ChallengePartitionLeakageError",
    "CheckpointCorruptError",
    "CheckpointMetadata",
    "CheckpointMissingCompleteMarkerError",
    "CheckpointResumeError",
    "CheckpointRetentionPolicy",
    "CheckpointStore",
    "CheckpointTransactionState",
    "ComparisonReport",
    "ConcurrencyController",
    "ConcurrencyLimitError",
    "CpuGovernor",
    "DPOObjective",
    "DatasetLockError",
    "DatasetQualityGate",
    "DatasetQualityPolicy",
    "DatasetRevokedError",
    "DatasetUnapprovedError",
    "DatasetUnfrozenError",
    "DeterministicSampler",
    "DiskGovernor",
    "DiskSpaceExhaustedError",
    "EarlyStopping",
    "EvaluationDecision",
    "EvaluatorDecisionEngine",
    "ExecutionFingerprint",
    "GLOBAL_OPERATIONAL_LEDGER",
    "GoldenHoldoutViolationError",
    "GovernanceCheckResult",
    "GpuFailureClass",
    "GpuGovernor",
    "GpuOOMError",
    "GpuOomOutcome",
    "GradedMarginLoss",
    "GradientExplosionError",
    "INVARIANTS",
    "ImbalanceAction",
    "InfLossError",
    "IntegrityMismatchError",
    "InvariantEnforcementLevel",
    "JobLease",
    "JobLeaseHeldError",
    "JobStateMachine",
    "KTOObjective",
    "LoRATrainerBackend",
    "LossStagnationError",
    "LossTracker",
    "MemoryGovernor",
    "MemoryLimits",
    "ModelArchitectureSpec",
    "ModelCompatibilityChecker",
    "ModelCompatibilityReport",
    "ModelIncompatibleError",
    "NaNLossError",
    "NonfiniteParameterError",
    "NumericalFaultClass",
    "NumericalPolicy",
    "NumericalStabilityMonitor",
    "OfflineTrainer",
    "OperationalEvidenceLedger",
    "OperationalInvariant",
    "OperationalTestEvidence",
    "PartitionEvaluationResult",
    "PartitionGuard",
    "PartitionLeakageError",
    "PartitionSampleManifest",
    "PrecisionMode",
    "QualityCheckReport",
    "QualityGateError",
    "RecoveryState",
    "ReproducibilityFingerprint",
    "ResourceLimitExceededError",
    "ResumeCompatibilityFingerprint",
    "RevocationGraph",
    "RevocationRecord",
    "RunIdentity",
    "SampleCollator",
    "ScopeMismatchError",
    "SecurityPolicy",
    "SecurityPolicyError",
    "SplitBrainDetectedError",
    "StateTransitionError",
    "StateTransitionRecord",
    "SupervisorLeaseManager",
    "SupervisorOptions",
    "TFIDFLogisticBaselineBackend",
    "TestExecutionClassification",
    "TimeoutExhaustedError",
    "ToleranceProfile",
    "TorchPreferenceTrainerBackend",
    "TorchSFTTrainerBackend",
    "TrainResult",
    "TrainerBackend",
    "TrainingBudget",
    "TrainingConfig",
    "TrainingError",
    "TrainingExecutionController",
    "TrainingGovernance",
    "TrainingInputLock",
    "TrainingJobState",
    "TrainingResourcePolicy",
    "TrainingSupervisor",
    "TrainingWorkerChild",
    "WeightedCrossEntropyLoss",
    "WeightedFocalLoss",
    "WindowsJobObject",
    "WorkerCrashError",
    "WorkerIdentityEnvelope",
    "WorkerUnresponsiveError",
    "check_numerical_equivalence",
    "classify_gpu_failure",
    "compute_wilson_interval",
    "get_backend_manifest",
    "get_loss_strategy_for_purpose",
    "get_trainer_backend",
    "is_safe_to_reap",
    "validate_preflight",
]
