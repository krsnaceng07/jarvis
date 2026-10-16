"""jarvis_learning.training.budget — multi-dimensional training budget and limits.

Tracks and enforces budget boundaries across steps, tokens, wall time, CPU time,
samples, checkpoints, and disk usage to prevent runaway resource consumption.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Any

from .errors import BudgetExhaustedError, TimeoutExhaustedError


class BudgetExhaustionReason(enum.StrEnum):
    """Specific dimension that breached the training budget."""

    MAX_EPOCHS_REACHED = "MAX_EPOCHS_REACHED"
    MAX_STEPS_REACHED = "MAX_STEPS_REACHED"
    MAX_TOKENS_REACHED = "MAX_TOKENS_REACHED"
    MAX_SAMPLES_REACHED = "MAX_SAMPLES_REACHED"
    WALL_TIME_EXHAUSTED = "WALL_TIME_EXHAUSTED"
    CPU_TIME_EXHAUSTED = "CPU_TIME_EXHAUSTED"
    CHECKPOINT_LIMIT_REACHED = "CHECKPOINT_LIMIT_REACHED"
    DISK_USAGE_EXCEEDED = "DISK_USAGE_EXCEEDED"


@dataclass(frozen=True, slots=True)
class TrainingBudget:
    """Multi-dimensional boundaries for a single training run."""

    max_epochs: int = 30
    max_steps: int = 10_000
    max_tokens: int = 50_000_000
    max_samples: int = 100_000
    max_wall_time_minutes: float = 60.0
    max_cpu_seconds: float = 3600.0
    max_checkpoint_count: int = 10
    max_disk_usage_mb: float = 2048.0


@dataclass(slots=True)
class BudgetTracker:
    """Tracks consumption against a TrainingBudget and enforces limits."""

    budget: TrainingBudget
    epochs_completed: int = 0
    steps_completed: int = 0
    tokens_processed: int = 0
    samples_processed: int = 0
    checkpoints_saved: int = 0
    current_disk_usage_mb: float = 0.0
    start_time: float = field(default_factory=time.monotonic)
    start_cpu_time: float = field(default_factory=time.process_time)

    def record_step(self, tokens: int = 0, samples: int = 1) -> None:
        """Record progress of a single training step."""
        self.steps_completed += 1
        self.tokens_processed += tokens
        self.samples_processed += samples

    def record_epoch(self) -> None:
        """Record completion of an epoch."""
        self.epochs_completed += 1

    def record_checkpoint(self, disk_mb_added: float = 0.0) -> None:
        """Record checkpoint write and disk usage."""
        self.checkpoints_saved += 1
        self.current_disk_usage_mb += disk_mb_added

    def elapsed_wall_seconds(self) -> float:
        """Elapsed monotonic wall-clock seconds."""
        return time.monotonic() - self.start_time

    def elapsed_wall_minutes(self) -> float:
        """Elapsed wall-clock minutes."""
        return self.elapsed_wall_seconds() / 60.0

    def elapsed_cpu_seconds(self) -> float:
        """Elapsed process CPU seconds."""
        return time.process_time() - self.start_cpu_time

    def check_limits(self, raise_on_exhaustion: bool = False) -> BudgetExhaustionReason | None:
        """Check all dimensions. Returns the first exhaustion reason if breached."""
        if self.epochs_completed >= self.budget.max_epochs:
            if raise_on_exhaustion:
                raise BudgetExhaustedError(
                    f"Max epochs reached ({self.epochs_completed}/{self.budget.max_epochs})",
                    budget_dimension=BudgetExhaustionReason.MAX_EPOCHS_REACHED.value,
                )
            return BudgetExhaustionReason.MAX_EPOCHS_REACHED

        if self.steps_completed >= self.budget.max_steps:
            if raise_on_exhaustion:
                raise BudgetExhaustedError(
                    f"Max steps reached ({self.steps_completed}/{self.budget.max_steps})",
                    budget_dimension=BudgetExhaustionReason.MAX_STEPS_REACHED.value,
                )
            return BudgetExhaustionReason.MAX_STEPS_REACHED

        if self.tokens_processed >= self.budget.max_tokens:
            if raise_on_exhaustion:
                raise BudgetExhaustedError(
                    f"Max tokens processed ({self.tokens_processed}/{self.budget.max_tokens})",
                    budget_dimension=BudgetExhaustionReason.MAX_TOKENS_REACHED.value,
                )
            return BudgetExhaustionReason.MAX_TOKENS_REACHED

        if self.samples_processed >= self.budget.max_samples:
            if raise_on_exhaustion:
                raise BudgetExhaustedError(
                    f"Max samples processed ({self.samples_processed}/{self.budget.max_samples})",
                    budget_dimension=BudgetExhaustionReason.MAX_SAMPLES_REACHED.value,
                )
            return BudgetExhaustionReason.MAX_SAMPLES_REACHED

        if self.elapsed_wall_minutes() >= self.budget.max_wall_time_minutes:
            if raise_on_exhaustion:
                raise TimeoutExhaustedError(
                    f"Max wall time exceeded ({self.elapsed_wall_minutes():.1f}/{self.budget.max_wall_time_minutes:.1f} min)"
                )
            return BudgetExhaustionReason.WALL_TIME_EXHAUSTED

        if self.elapsed_cpu_seconds() >= self.budget.max_cpu_seconds:
            if raise_on_exhaustion:
                raise BudgetExhaustedError(
                    f"Max CPU time exceeded ({self.elapsed_cpu_seconds():.1f}/{self.budget.max_cpu_seconds:.1f} s)",
                    budget_dimension=BudgetExhaustionReason.CPU_TIME_EXHAUSTED.value,
                )
            return BudgetExhaustionReason.CPU_TIME_EXHAUSTED

        if self.checkpoints_saved >= self.budget.max_checkpoint_count:
            if raise_on_exhaustion:
                raise BudgetExhaustedError(
                    f"Max checkpoints reached ({self.checkpoints_saved}/{self.budget.max_checkpoint_count})",
                    budget_dimension=BudgetExhaustionReason.CHECKPOINT_LIMIT_REACHED.value,
                )
            return BudgetExhaustionReason.CHECKPOINT_LIMIT_REACHED

        if self.current_disk_usage_mb >= self.budget.max_disk_usage_mb:
            if raise_on_exhaustion:
                raise BudgetExhaustedError(
                    f"Max disk usage exceeded ({self.current_disk_usage_mb:.1f}/{self.budget.max_disk_usage_mb:.1f} MB)",
                    budget_dimension=BudgetExhaustionReason.DISK_USAGE_EXCEEDED.value,
                )
            return BudgetExhaustionReason.DISK_USAGE_EXCEEDED

        return None

    def to_dict(self) -> dict[str, Any]:
        """Diagnostic state serialization."""
        return {
            "epochs_completed": self.epochs_completed,
            "steps_completed": self.steps_completed,
            "tokens_processed": self.tokens_processed,
            "samples_processed": self.samples_processed,
            "checkpoints_saved": self.checkpoints_saved,
            "current_disk_usage_mb": round(self.current_disk_usage_mb, 2),
            "elapsed_wall_seconds": round(self.elapsed_wall_seconds(), 2),
            "elapsed_cpu_seconds": round(self.elapsed_cpu_seconds(), 2),
        }
