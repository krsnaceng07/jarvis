"""Detached Background Worker Pool for Autonomous Claws — JARVIS Autonomous Architecture.

Executes autonomous Claw jobs concurrently in the background without blocking
the Gateway or conversational turns. Enforces concurrency limits, timeouts,
error handling, and audit ledger tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable

from .base import Claw, ClawExecutionContext
from .task_queue import ClawTaskQueue
from .types import ClawJob, ClawResult

logger = logging.getLogger("jarvis.claws.worker_pool")


class ClawWorkerPool:
    """Detached background worker pool that processes queued Claw jobs."""

    def __init__(
        self,
        task_queue: ClawTaskQueue,
        claw_registry: dict[str, Claw],
        concurrency: int = 4,
        workspace_root: Path | None = None,
        poll_interval: float = 1.0,
        notify_fn: Callable[[str, str, str], None] | None = None,
        outbound_fn: Callable[[str, str, str | None], None] | None = None,
    ) -> None:
        self.task_queue = task_queue
        self.claw_registry = claw_registry
        self.concurrency = max(1, concurrency)
        self.workspace_root = workspace_root or Path.cwd()
        self.poll_interval = poll_interval
        self.notify_fn = notify_fn
        self.outbound_fn = outbound_fn

        self._running = False
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        """Start background worker tasks."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        for i in range(self.concurrency):
            task = asyncio.create_task(self._worker_loop(i), name=f"claw-worker-{i}")
            self._worker_tasks.append(task)
        logger.info(
            "ClawWorkerPool started with %d workers (concurrency limit: %d)",
            len(self._worker_tasks),
            self.concurrency,
        )

    async def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stop background worker tasks."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        for task in self._worker_tasks:
            task.cancel()
        done, pending = await asyncio.wait(self._worker_tasks, timeout=timeout)
        self._worker_tasks.clear()
        logger.info("ClawWorkerPool stopped cleanly.")

    async def _worker_loop(self, worker_index: int) -> None:
        """Internal worker loop polling for pending jobs."""
        logger.debug("Claw worker %d started", worker_index)
        while self._running:
            try:
                # Dequeue next pending job
                job = self.task_queue.dequeue_next()
                if job is None:
                    # No pending jobs, wait for poll_interval or stop event
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                        break
                    except asyncio.TimeoutError:
                        continue

                # Process job within semaphore
                async with self._semaphore:
                    await self._execute_job(job)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Worker %d encountered error in worker loop: %s",
                    worker_index,
                    e,
                    exc_info=True,
                )
                await asyncio.sleep(self.poll_interval)

    async def _execute_job(self, job: ClawJob) -> None:
        """Execute a single ClawJob with timeout, error handling, and audit recording."""
        claw = self.claw_registry.get(job.claw_id)
        if claw is None:
            logger.warning(
                "Job %s requested unknown Claw %r; failing job",
                job.job_id,
                job.claw_id,
            )
            self.task_queue.mark_failed(
                job.job_id, f"Claw '{job.claw_id}' not found in registry", retryable=False
            )
            return

        state_dir = self.task_queue.db_path.parent
        ctx = ClawExecutionContext(
            job_id=job.job_id,
            claw_id=job.claw_id,
            workspace_root=self.workspace_root,
            state_dir=state_dir,
            payload=job.payload,
            _checkpoint_fn=self.task_queue.save_checkpoint,
            _notify_fn=self.notify_fn,
            _outbound_fn=self.outbound_fn,
        )

        logger.info("Worker executing Claw %s (job %s)...", claw.name, job.job_id)
        start_time = time.monotonic()
        try:
            # Enforce claw timeout
            result = await asyncio.wait_for(claw.run(ctx), timeout=claw.timeout_seconds)
            duration_ms = (time.monotonic() - start_time) * 1000.0

            if not isinstance(result, ClawResult):
                result = ClawResult(
                    success=True,
                    output=result,
                    duration_ms=duration_ms,
                )
            else:
                # Update duration if not set
                if result.duration_ms <= 0:
                    result = ClawResult(
                        success=result.success,
                        output=result.output,
                        error=result.error,
                        duration_ms=duration_ms,
                        metrics=result.metrics,
                    )

            if result.success:
                self.task_queue.mark_completed(job.job_id, result)
                logger.info(
                    "Claw %s (job %s) completed successfully in %.2fms",
                    claw.name,
                    job.job_id,
                    duration_ms,
                )
            else:
                err_msg = result.error or "Unknown failure"
                will_retry = self.task_queue.mark_failed(job.job_id, err_msg, retryable=True)
                logger.warning(
                    "Claw %s (job %s) failed: %s (will_retry=%s)",
                    claw.name,
                    job.job_id,
                    err_msg,
                    will_retry,
                )

        except asyncio.TimeoutError:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            timeout_msg = f"Claw execution timed out after {claw.timeout_seconds:.1f}s"
            self.task_queue.mark_failed(job.job_id, timeout_msg, retryable=True)
            logger.warning(
                "Claw %s (job %s) timed out (%.2fms)",
                claw.name,
                job.job_id,
                duration_ms,
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000.0
            err_msg = f"Unhandled exception: {exc}"
            self.task_queue.mark_failed(job.job_id, err_msg, retryable=True)
            logger.error(
                "Claw %s (job %s) crashed: %s",
                claw.name,
                job.job_id,
                exc,
                exc_info=True,
            )


__all__ = ["ClawWorkerPool"]
