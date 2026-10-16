"""Background Reflection Worker with Cooperative Yielding.

Runs detached from the primary user interaction loop:
- Asynchronous bounded priority job queue
- Cooperative yielding / pause when live audio, voice, or user agent turns are active
- Crash-safe job status tracking
- Never blocks GUI, speech synthesis, or turn processing
"""

from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(order=True)
class ReflectionJob:
    priority: int  # Lower number = higher priority (e.g. 1 for critical failure, 10 for background consolidation)
    job_id: str = field(compare=False)
    payload: Dict[str, Any] = field(compare=False)
    status: JobStatus = field(default=JobStatus.QUEUED, compare=False)
    created_at: float = field(default_factory=time.time, compare=False)
    retries: int = field(default=0, compare=False)


class ReflectionWorker:
    """Manages asynchronous reflection jobs with cooperative execution."""

    def __init__(self, max_queue_size: int = 100) -> None:
        self.max_queue_size = max_queue_size
        self._queue: List[ReflectionJob] = []
        self._lock = threading.Lock()
        self._is_paused = False
        self._running = False
        self._completed_jobs: Dict[str, ReflectionJob] = {}

    def pause(self) -> None:
        """Called when live voice, audio capture, or active turn begins."""
        with self._lock:
            self._is_paused = True

    def resume(self) -> None:
        """Called when interactive user turns end and audio is idle."""
        with self._lock:
            self._is_paused = False

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._is_paused

    def enqueue_job(self, job_id: str, payload: Dict[str, Any], priority: int = 5) -> bool:
        with self._lock:
            if len(self._queue) >= self.max_queue_size:
                # Drop oldest low-priority job if at capacity
                self._queue.sort()
                self._queue.pop()  # Remove lowest priority item

            job = ReflectionJob(priority=priority, job_id=job_id, payload=payload)
            heapq.heappush(self._queue, job)
            return True

    def step(self, handler: Callable[[ReflectionJob], bool]) -> Optional[str]:
        """Execute a single job step cooperatively.

        Returns the job_id processed, or None if paused / empty.
        """
        job_to_run: Optional[ReflectionJob] = None
        with self._lock:
            if self._is_paused or not self._queue:
                return None
            job_to_run = heapq.heappop(self._queue)
            job_to_run.status = JobStatus.RUNNING

        try:
            success = handler(job_to_run)
            job_to_run.status = JobStatus.COMPLETED if success else JobStatus.FAILED
        except Exception:
            job_to_run.status = JobStatus.FAILED

        with self._lock:
            self._completed_jobs[job_to_run.job_id] = job_to_run

        return job_to_run.job_id

    def pending_count(self) -> int:
        with self._lock:
            return len(self._queue)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        with self._lock:
            for job in self._queue:
                if job.job_id == job_id:
                    return job.status
            if job_id in self._completed_jobs:
                return self._completed_jobs[job_id].status
            return None
