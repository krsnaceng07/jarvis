"""jarvis_learning.training.loss_tracker — loss tracking, plateau detection, and early stopping.

Maintains loss history across epochs, computes moving averages, and signals
early stopping when validation metrics plateau.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EarlyStopping:
    """Monitors validation metric and determines when training should stop."""

    patience: int = 4
    min_delta: float = 0.001
    mode: str = "min"  # "min" for loss, "max" for accuracy
    best_value: float = field(default=float("inf"))
    wait_count: int = 0
    stopped_epoch: int = -1

    def __post_init__(self) -> None:
        if self.mode == "max":
            self.best_value = float("-inf")

    def step(self, current_value: float, epoch: int) -> bool:
        """Update with latest metric; returns True if training should stop."""
        if self.mode == "min":
            improved = current_value < (self.best_value - self.min_delta)
        else:
            improved = current_value > (self.best_value + self.min_delta)

        if improved:
            self.best_value = current_value
            self.wait_count = 0
            return False
        else:
            self.wait_count += 1
            if self.wait_count >= self.patience:
                self.stopped_epoch = epoch
                logger.info(
                    "Early stopping triggered at epoch %d: metric %f did not improve for %d epochs",
                    epoch,
                    current_value,
                    self.wait_count,
                )
                return True
            return False


@dataclass(slots=True)
class LossTracker:
    """Tracks training and validation loss progression across epochs."""

    train_losses: list[float] = field(default_factory=list)
    val_losses: list[float] = field(default_factory=list)
    early_stopping: EarlyStopping = field(default_factory=EarlyStopping)

    def record_epoch(self, train_loss: float, val_loss: float | None = None) -> bool:
        """Record epoch losses and evaluate early stopping; returns True if early stop triggered."""
        self.train_losses.append(train_loss)
        if val_loss is not None:
            self.val_losses.append(val_loss)
            epoch = len(self.val_losses)
            return self.early_stopping.step(val_loss, epoch)
        return False

    def moving_average(self, window: int = 3) -> float:
        """Compute moving average of the last `window` training loss points."""
        if not self.train_losses:
            return 0.0
        recent = self.train_losses[-window:]
        return sum(recent) / len(recent)

    def to_dict(self) -> dict[str, Any]:
        """Diagnostic state serialization."""
        return {
            "epoch_count": len(self.train_losses),
            "latest_train_loss": self.train_losses[-1] if self.train_losses else None,
            "latest_val_loss": self.val_losses[-1] if self.val_losses else None,
            "best_val_loss": (
                self.early_stopping.best_value
                if self.early_stopping.best_value != float("inf")
                else None
            ),
            "early_stopping_triggered": self.early_stopping.stopped_epoch >= 0,
            "stopped_epoch": self.early_stopping.stopped_epoch,
        }
