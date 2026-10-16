"""jarvis_learning.training.config — training run configuration.

Controls dataset inputs, learning rate, epochs, early stopping, batching,
budget limits, and reproducibility seeds.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .batching import BatchPolicy
from .budget import TrainingBudget
from .reproducibility import PrecisionMode


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """Hyperparameters and operational limits for an offline training job."""

    target: str
    dataset_dir: str
    output_dir: str = ""
    epochs: int = 30
    batch_size: int = 16
    learning_rate: float = 0.05
    early_stopping_patience: int = 4
    min_samples_required: int = 10  # Safeguard: fail with insufficient_data if below this
    min_accuracy_gain: float = 0.02  # Must beat baseline by 2%
    l2_reg: float = 0.001
    random_seed: int = 42
    backend_type: str = "tfidf_logistic"
    precision_mode: PrecisionMode = PrecisionMode.CPU_DETERMINISTIC
    budget: TrainingBudget = field(default_factory=TrainingBudget)
    batch_policy: BatchPolicy = field(default_factory=BatchPolicy)
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_config_hash(self) -> str:
        """Deterministic SHA-256 digest of configuration hyperparameters."""
        payload = {
            "backend_type": self.backend_type,
            "batch_size": self.batch_size,
            "dataset_dir": str(self.dataset_dir),
            "early_stopping_patience": self.early_stopping_patience,
            "epochs": self.epochs,
            "l2_reg": self.l2_reg,
            "learning_rate": self.learning_rate,
            "min_accuracy_gain": self.min_accuracy_gain,
            "precision_mode": self.precision_mode.value,
            "random_seed": self.random_seed,
            "target": self.target,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
