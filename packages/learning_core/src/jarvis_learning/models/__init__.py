"""jarvis_learning.models — local task models, baselines, and calibration."""

from __future__ import annotations

from .arguments import ArgumentBuildResult, DeterministicArgumentBuilder
from .artifact import ModelArtifactBundle, ModelManifest
from .base import InferenceBackend, LocalModel, ModelTargetMismatchError, ToolPrediction
from .baseline import BaselineEvaluation, FrequencyBaseline, TFIDFLogisticBaseline
from .calibration import CalibrationMetrics, ConfidenceCalibrator
from .decision_trace import DecisionTrace
from .lifecycle import (
    InvalidLifecycleTransitionError,
    ModelLifecycle,
    ModelStatus,
    StatusTransition,
)
from .memory_reranker import MemoryRerankerModel, MemoryUsageEvidence
from .strategy_predictor import StrategyCandidateRecord, StrategyPredictorModel
from .tool_policy import ToolPolicyModel

__all__ = [
    "ArgumentBuildResult",
    "BaselineEvaluation",
    "CalibrationMetrics",
    "ConfidenceCalibrator",
    "DecisionTrace",
    "DeterministicArgumentBuilder",
    "FrequencyBaseline",
    "InferenceBackend",
    "InvalidLifecycleTransitionError",
    "LocalModel",
    "MemoryRerankerModel",
    "MemoryUsageEvidence",
    "ModelArtifactBundle",
    "ModelLifecycle",
    "ModelManifest",
    "ModelStatus",
    "ModelTargetMismatchError",
    "StatusTransition",
    "StrategyCandidateRecord",
    "StrategyPredictorModel",
    "TFIDFLogisticBaseline",
    "ToolPolicyModel",
    "ToolPrediction",
]
