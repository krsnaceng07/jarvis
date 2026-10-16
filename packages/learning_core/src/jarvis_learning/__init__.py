"""jarvis_learning — JARVIS self-learning and continual-learning engine.

Public API:
    from jarvis_learning import (
        LearningEngine,
        HardwareDetector,
        ModelRegistry,
        OfflineTrainer,
        ModelRouter,
    )
"""

from __future__ import annotations

from .datasets.builder import DatasetBuildResult, DatasetBuilder, DatasetConfig
from .datasets.manifest import DatasetManifest
from .datasets.schema import DatasetSample, DatasetTarget, FailureType, LabelQuality
from .engine import LearningEngine, LearningRetrievalContext
from .evaluation.benchmark import (
    BenchmarkCase,
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkSuiteResult,
)
from .evaluation.regression import RegressionGate, RegressionResult
from .events import LearningEvent, LearningEventBus, LearningEventType
from .experience import Experience, Lesson, TaskEpisode, TaskStep, generate_id, now_ms
from .feedback import Feedback, FeedbackCollector, ImplicitFeedbackDetector
from .hardware.detector import HardwareDetector
from .hardware.profile import ComputeProfile, ComputeTier, HardwareSpecs
from .knowledge import KnowledgeEntry, KnowledgeStore
from .models.base import LocalModel, ModelTargetMismatchError, ToolPrediction
from .models.baseline import FrequencyBaseline, TFIDFLogisticBaseline
from .models.calibration import ConfidenceCalibrator
from .models.decision_trace import DecisionTrace
from .models.lifecycle import InvalidLifecycleTransitionError, ModelLifecycle, ModelStatus
from .models.registry import ModelRecord, ModelRegistry
from .procedures import Procedure, ProcedureStep, ProcedureStore
from .reflection import CritiqueResult, LearningCritic, ReflectionEngine
from .reward import RewardScorer, RewardWeights
from .routing.guard import GuardDecision, LocalDecisionGuard
from .routing.health import HealthDecision, RuntimeHealthMonitor
from .routing.ood import DistributionGuard, OODResult
from .routing.promotion import PromotionDecision, PromotionManager, ShadowQualification
from .routing.router import ModelRouter, RouterConfig, RoutingResult
from .routing.shadow import ShadowExecutor, ShadowObservation, ShadowPerformanceMetrics
from .strategies import FailurePattern, Strategy, StrategyStore
from .training.comparison import BaselineComparator, ComparisonReport
from .training.config import TrainingConfig
from .training.resource_policy import TrainingExecutionController, TrainingResourcePolicy
from .training.trainer import OfflineTrainer, TrainResult
from .verification import (
    ClaimVerifier,
    CompositeVerifier,
    OutcomeVerifier,
    ToolResultVerifier,
    VerificationResult,
)

# Phase 5: Autonomous Reflection & Strategy Lifecycle
from .causal_critic import AttributionStatus, CausalCritic, CausalCritique, CausalFailureType
from .compatibility import CompatibilityFingerprint
from .confidence_engine import BayesianConfidenceState
from .evidence_model import EvidenceSource, EvidenceTrustLevel, ExperienceEvidence
from .feedback_attribution import (
    AttributionCategory,
    FeedbackAttributionResult,
    FeedbackAttributor,
    FeedbackSignal,
    FeedbackSourceType,
)
from .path_quality import PathEvaluation, PathQualityEvaluator, SuccessQuality
from .precondition_contract import PreconditionContract, StateProbe
from .recovery import RecoveryPlan
from .reflection_worker import JobStatus, ReflectionJob, ReflectionWorker
from .strategy_conflict import ConflictResolver, StrategyCandidate, StrategyFingerprint
from .strategy_lifecycle import (
    LifecycleAuditEntry,
    RiskTierConfig,
    StrategyLifecycleManager,
    StrategyLifecycleState,
)
from .task_reflection import TaskEpisodeReflection, TaskEpisodeReflector, TaskStepRecord

__all__ = [
    # Engine
    "LearningEngine",
    "LearningRetrievalContext",
    # Events
    "LearningEvent",
    "LearningEventBus",
    "LearningEventType",
    # Experience
    "Experience",
    "Lesson",
    "TaskEpisode",
    "TaskStep",
    "generate_id",
    "now_ms",
    # Feedback
    "Feedback",
    "FeedbackCollector",
    "ImplicitFeedbackDetector",
    # Knowledge
    "KnowledgeEntry",
    "KnowledgeStore",
    # Procedures
    "Procedure",
    "ProcedureStep",
    "ProcedureStore",
    # Reflection
    "CritiqueResult",
    "LearningCritic",
    "ReflectionEngine",
    # Reward
    "RewardScorer",
    "RewardWeights",
    # Strategies
    "FailurePattern",
    "Strategy",
    "StrategyStore",
    # Verification
    "ClaimVerifier",
    "CompositeVerifier",
    "OutcomeVerifier",
    "ToolResultVerifier",
    "VerificationResult",
    # Wave 2 Datasets & Evaluation
    "DatasetBuildResult",
    "DatasetBuilder",
    "DatasetConfig",
    "DatasetManifest",
    "DatasetSample",
    "DatasetTarget",
    "FailureType",
    "LabelQuality",
    "BenchmarkCase",
    "BenchmarkResult",
    "BenchmarkRunner",
    "BenchmarkSuiteResult",
    "RegressionGate",
    "RegressionResult",
    # Wave 3 Hardware & Profiling
    "ComputeProfile",
    "ComputeTier",
    "HardwareDetector",
    "HardwareSpecs",
    # Wave 3 Models & Calibration
    "ConfidenceCalibrator",
    "DecisionTrace",
    "FrequencyBaseline",
    "InvalidLifecycleTransitionError",
    "LocalModel",
    "ModelLifecycle",
    "ModelRecord",
    "ModelRegistry",
    "ModelStatus",
    "ModelTargetMismatchError",
    "TFIDFLogisticBaseline",
    "ToolPrediction",
    # Wave 3 Training & Baselines
    "BaselineComparator",
    "ComparisonReport",
    "OfflineTrainer",
    "TrainResult",
    "TrainingConfig",
    "TrainingExecutionController",
    "TrainingResourcePolicy",
    # Wave 3 Routing & Governance
    "DistributionGuard",
    "GuardDecision",
    "HealthDecision",
    "LocalDecisionGuard",
    "ModelRouter",
    "OODResult",
    "PromotionDecision",
    "PromotionManager",
    "RouterConfig",
    "RoutingResult",
    "RuntimeHealthMonitor",
    "ShadowExecutor",
    "ShadowObservation",
    "ShadowPerformanceMetrics",
    "ShadowQualification",
    # Phase 5 Autonomous Reflection & Strategy Lifecycle
    "AttributionCategory",
    "AttributionStatus",
    "BayesianConfidenceState",
    "CausalCritic",
    "CausalCritique",
    "CausalFailureType",
    "CompatibilityFingerprint",
    "ConflictResolver",
    "EvidenceSource",
    "EvidenceTrustLevel",
    "ExperienceEvidence",
    "FeedbackAttributionResult",
    "FeedbackAttributor",
    "FeedbackSignal",
    "FeedbackSourceType",
    "JobStatus",
    "LifecycleAuditEntry",
    "PathEvaluation",
    "PathQualityEvaluator",
    "PreconditionContract",
    "RecoveryPlan",
    "ReflectionJob",
    "ReflectionWorker",
    "RiskTierConfig",
    "StateProbe",
    "StrategyCandidate",
    "StrategyFingerprint",
    "StrategyLifecycleManager",
    "StrategyLifecycleState",
    "SuccessQuality",
    "TaskEpisodeReflection",
    "TaskEpisodeReflector",
    "TaskStepRecord",
]
