"""jarvis_learning.training.resource_policy — resource limits for offline training.

Prevents background training from saturating CPU or RAM, and provides
clean pausing/cancellation during interactive user tasks.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TrainingResourcePolicy:
    """Resource constraints for model training execution."""

    max_threads: int = 3  # Limit thread count to avoid laptop freezing
    max_ram_percent: float = 40.0  # Maximum fraction of system RAM allowed
    max_memory_mb: int = 512  # Max memory limit in megabytes
    max_training_minutes: int = 15  # Hard training timeout
    allow_background_training: bool = True
    pause_on_interactive_activity: bool = True

    def apply_thread_limits(self) -> None:
        """Apply thread limits to active ML libraries if present."""
        try:
            import torch

            torch.set_num_threads(self.max_threads)
            logger.debug("Applied torch.set_num_threads(%d)", self.max_threads)
        except ImportError:
            pass


class TrainingExecutionController:
    """Coordinates cooperative pausing and cancellation of training runs."""

    def __init__(self, policy: TrainingResourcePolicy | None = None) -> None:
        self.policy = policy or TrainingResourcePolicy()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Unpaused by default
        self._cancel_flag = False

    def pause(self, reason: str = "interactive_activity") -> None:
        """Pause training."""
        if self._pause_event.is_set():
            self._pause_event.clear()
            logger.info("Training paused: %s", reason)

    def resume(self) -> None:
        """Resume training."""
        if not self._pause_event.is_set():
            self._pause_event.set()
            logger.info("Training resumed")

    def cancel(self) -> None:
        """Cancel training."""
        self._cancel_flag = True
        self._pause_event.set()  # Unblock if currently paused so it can exit
        logger.info("Training cancellation requested")

    def check_checkpoint(self) -> bool:
        """Called between epochs/batches. Returns False if cancelled, waits if paused."""
        if self._cancel_flag:
            return False
        # Wait if paused (blocks thread until resume() or cancel() is called)
        self._pause_event.wait()
        return not self._cancel_flag
