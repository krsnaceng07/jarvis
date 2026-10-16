"""jarvis_learning.models.base — base interfaces for local learning models.

Defines the InferenceBackend protocol, LocalModel abstract base class,
and standard prediction payloads.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class ModelTargetMismatchError(ValueError):
    """Raised when a model artifact is loaded for an incompatible target."""


@dataclass(frozen=True, slots=True)
class ToolPrediction:
    """Output from Model A (Tool Selection Policy).

    Advisory neural prediction. Contains tool name and intent classification.
    NEVER contains raw shell commands or unauthorized execution scripts.
    """

    tool_name: str
    raw_confidence: float = 0.0
    calibrated_confidence: float = 0.0
    confidence: float = 0.0
    intent: str = ""
    model_id: str = ""
    model_version: str = ""
    task_family: str = ""
    label_id: int | str = 0
    ood_score: float | None = None
    latency_ms: float = 0.0
    is_finite: bool = True
    prediction_id: str = ""
    action_type: str = "read"  # "read", "navigate", "set_state", "execute"
    risk_level: str = "low"  # "low", "medium", "high", "destructive"
    argument_strategy: str = (
        "deterministic"  # "deterministic", "context_extraction", "llm_required"
    )
    required_context_fields: tuple[str, ...] = ()
    alternatives: tuple[tuple[str, float], ...] = ()


@runtime_checkable
class InferenceBackend(Protocol):
    """Protocol for model execution runtimes (Fallback, Scikit-learn, PyTorch)."""

    def load(self, artifact_dir: Path) -> None:
        """Load weights, tokenizers, and encoders from artifact directory."""
        ...

    def predict(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Perform forward inference on input features."""
        ...

    def unload(self) -> None:
        """Release in-memory weights and free RAM/VRAM."""
        ...


class LocalModel(ABC):
    """Abstract base class for all JARVIS local task models."""

    def __init__(self, target: str, model_id: str, version: str) -> None:
        self.target = target
        self.model_id = model_id
        self.version = version
        self._is_loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @abstractmethod
    def load(self, artifact_dir: Path) -> None:
        """Load model artifacts and verify integrity."""
        ...

    @abstractmethod
    def predict(self, input_data: dict[str, Any]) -> Any:
        """Generate a prediction from input features."""
        ...

    @abstractmethod
    def unload(self) -> None:
        """Unload model from memory."""
        ...
