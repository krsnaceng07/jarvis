"""jarvis_learning.worker — Separate background process worker for CPU model training."""

from __future__ import annotations

import concurrent.futures
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jarvis_learning.training.config import TrainingConfig
from jarvis_learning.training.resource_policy import (
    TrainingExecutionController,
    TrainingResourcePolicy,
)
from jarvis_learning.training.trainer import OfflineTrainer, TrainResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TrainingJobStatus:
    job_id: str
    target: str
    status: str  # "pending", "running", "completed", "failed", "aborted"
    progress: float
    error_message: str = ""


class TrainingWorker:
    """Manages asynchronous offline training in a detached worker pool.

    Guarantees:
    - Never blocks the active voice/chat foreground loop.
    - Obeys thread and RAM caps via TrainingResourcePolicy.
    - Provides cancellation and pause on active interaction.
    """

    def __init__(self, policy: TrainingResourcePolicy | None = None) -> None:
        self.policy = policy or TrainingResourcePolicy(max_threads=3, max_ram_percent=40.0)
        self.controller = TrainingExecutionController(self.policy)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="learning_worker"
        )
        self._current_future: concurrent.futures.Future[Any] | None = None
        self._is_paused = False
        self._aborted = False
        self._running = True

    def is_running(self) -> bool:
        return self._running

    def is_paused(self) -> bool:
        return self._is_paused

    def is_busy(self) -> bool:
        return self._current_future is not None and not self._current_future.done()

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False
        self.shutdown()

    def pause(self) -> None:
        """Signals worker to yield CPU priority during active voice/chat."""
        self._is_paused = True
        self.controller.pause()
        logger.info("training worker paused for active interaction")

    def resume(self) -> None:
        """Resumes background training once interaction is idle."""
        self._is_paused = False
        self.controller.resume()
        logger.info("training worker resumed")

    def abort(self) -> None:
        """Cancels active training job immediately."""
        self._aborted = True
        self.controller.cancel()
        if self._current_future and not self._current_future.done():
            self._current_future.cancel()
        logger.info("training worker job aborted")

    def enqueue(
        self,
        target: str,
        fn: Callable[[], Any],
        callback: Callable[[Any], None] | None = None,
    ) -> str:
        """Enqueues an arbitrary offline task in the background worker."""
        if not self._running:
            raise RuntimeError("TrainingWorker is stopped")

        self._aborted = False
        self._is_paused = False

        def _run() -> Any:
            res = fn()
            if callback:
                try:
                    callback(res)
                except Exception as e:
                    logger.error("error in worker callback: %s", e)
            return res

        self._current_future = self._executor.submit(_run)
        return f"job_{target}"

    def submit_job(
        self,
        config: TrainingConfig,
        on_complete: Callable[[TrainResult], None] | None = None,
    ) -> str:
        """Submits an offline training job to the detached worker."""
        if self.is_busy():
            raise RuntimeError("TrainingWorker is currently busy executing another training job")

        self._aborted = False
        self._is_paused = False

        def _run() -> TrainResult:
            trainer = OfflineTrainer(resource_policy=self.policy)
            res = trainer.train(config)
            if on_complete:
                try:
                    on_complete(res)
                except Exception as e:
                    logger.error("error in training on_complete callback: %s", e)
            return res

        self._current_future = self._executor.submit(_run)
        return f"job_{config.target}_{Path(config.output_dir).name}"

    def wait_for_completion(self, timeout_seconds: float = 30.0) -> Any:
        """Synchronously waits for active job to finish (used in CI/tests and CLI)."""
        if self._current_future is None:
            return None
        return self._current_future.result(timeout=timeout_seconds)

    def shutdown(self) -> None:
        self._running = False
        self._executor.shutdown(wait=False)
