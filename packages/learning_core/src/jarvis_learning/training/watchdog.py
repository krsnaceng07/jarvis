"""jarvis_learning.training.watchdog — worker heartbeat tracking and deadlock detection.

Supervises worker child processes to detect frozen threads, CUDA kernel deadlocks,
and unresponsive IPC communication.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .errors import WorkerUnresponsiveError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkerWatchdog:
    """Supervises child process liveness and heartbeat progression."""

    heartbeat_timeout_seconds: float = 30.0
    progress_timeout_seconds: float = 120.0
    last_heartbeat_time: float = field(default_factory=time.monotonic)
    last_progress_time: float = field(default_factory=time.monotonic)
    heartbeat_count: int = 0
    progress_count: int = 0

    def record_heartbeat(self) -> None:
        """Called upon receiving a heartbeat packet from the worker child."""
        self.last_heartbeat_time = time.monotonic()
        self.heartbeat_count += 1

    def record_progress(self) -> None:
        """Called upon receiving a training progress (step/epoch) packet."""
        now = time.monotonic()
        self.last_heartbeat_time = now
        self.last_progress_time = now
        self.progress_count += 1

    def time_since_last_heartbeat(self) -> float:
        """Monotonic seconds since last received heartbeat."""
        return time.monotonic() - self.last_heartbeat_time

    def time_since_last_progress(self) -> float:
        """Monotonic seconds since last step or epoch progress."""
        return time.monotonic() - self.last_progress_time

    def is_heartbeat_expired(self) -> bool:
        """Check if worker heartbeat has timed out."""
        return self.time_since_last_heartbeat() > self.heartbeat_timeout_seconds

    def is_progress_expired(self) -> bool:
        """Check if worker has stopped making training progress."""
        return self.time_since_last_progress() > self.progress_timeout_seconds

    def check_liveness(self, raise_on_deadlock: bool = True) -> bool:
        """Verify worker is alive; raises WorkerUnresponsiveError if deadlocked."""
        if self.is_heartbeat_expired():
            msg = (
                f"Worker unresponsive: no heartbeat for "
                f"{self.time_since_last_heartbeat():.1f}s "
                f"(timeout={self.heartbeat_timeout_seconds}s)"
            )
            logger.error(msg)
            if raise_on_deadlock:
                raise WorkerUnresponsiveError(msg)
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Diagnostic snapshot."""
        return {
            "heartbeat_count": self.heartbeat_count,
            "progress_count": self.progress_count,
            "seconds_since_heartbeat": round(self.time_since_last_heartbeat(), 2),
            "seconds_since_progress": round(self.time_since_last_progress(), 2),
            "is_expired": self.is_heartbeat_expired(),
        }
