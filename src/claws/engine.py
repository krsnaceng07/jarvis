"""Autonomous Claws Engine — JARVIS Autonomous Architecture (Section 8).

Orchestrates Cron Core timers, SQLite persistent task queues, detached background
worker pools, and autonomous Claws.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from jarvis_cron_core.runner import CronRunner, get_default_cron_runner
from jarvis_cron_core.types import CronDecl

from .base import Claw, ClawExecutionContext
from .builtins import (
    DatabaseMaintenanceClaw,
    DigestClaw,
    RepositoryHealthClaw,
    SystemMonitorClaw,
    WebMonitorClaw,
)
from .task_queue import ClawTaskQueue
from .types import ClawJob, ClawPriority, ClawResult
from .worker_pool import ClawWorkerPool

logger = logging.getLogger("jarvis.claws.engine")


class ClawsEngine:
    """Central engine for autonomous background worker daemons in JARVIS."""

    def __init__(
        self,
        task_queue: ClawTaskQueue | None = None,
        cron_runner: CronRunner | None = None,
        workspace_root: Path | None = None,
        concurrency: int = 4,
        notify_fn: Callable[[str, str, str], None] | None = None,
        outbound_fn: Callable[[str, str, str | None], None] | None = None,
    ) -> None:
        self.workspace_root = workspace_root or Path.cwd()
        self.task_queue = task_queue or ClawTaskQueue()
        self.cron_runner = cron_runner or get_default_cron_runner()
        self.notify_fn = notify_fn
        self.outbound_fn = outbound_fn

        self._claws: dict[str, Claw] = {}
        self.worker_pool = ClawWorkerPool(
            task_queue=self.task_queue,
            claw_registry=self._claws,
            concurrency=concurrency,
            workspace_root=self.workspace_root,
            notify_fn=self.notify_fn,
            outbound_fn=self.outbound_fn,
        )
        self._running = False

        # Register default built-in autonomous Claws
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register canonical system Claws."""
        self.register_claw(DatabaseMaintenanceClaw())
        self.register_claw(RepositoryHealthClaw())
        self.register_claw(SystemMonitorClaw())
        self.register_claw(DigestClaw())
        self.register_claw(WebMonitorClaw())

    def register_claw(self, claw: Claw) -> None:
        """Register a new autonomous Claw and wire its schedule to the CronRunner."""
        self._claws[claw.claw_id] = claw
        logger.info(
            "Registered Claw %s (id=%s, schedule=%r)",
            claw.name,
            claw.claw_id,
            claw.schedule,
        )

        if claw.enabled and claw.schedule:
            # Wire into CronRunner
            def _cron_handler(c_id: str = claw.claw_id) -> None:
                logger.info("Cron timer triggered Claw %s", c_id)
                self.dispatch_job(c_id)

            cron_decl = CronDecl(
                id=f"cron:{claw.claw_id}",
                schedule=claw.schedule,
                handler=_cron_handler,
                description=claw.description,
                enabled=claw.enabled,
            )
            self.cron_runner.add(cron_decl)

    def unregister_claw(self, claw_id: str) -> None:
        """Unregister a Claw by ID."""
        self._claws.pop(claw_id, None)
        self.cron_runner.remove(f"cron:{claw_id}")

    def get_claw(self, claw_id: str) -> Claw | None:
        return self._claws.get(claw_id)

    def list_claws(self) -> list[dict[str, Any]]:
        """List metadata of all registered Claws."""
        return [
            {
                "claw_id": c.claw_id,
                "name": c.name,
                "description": c.description,
                "schedule": c.schedule,
                "priority": c.priority.value,
                "enabled": c.enabled,
                "timeout_seconds": c.timeout_seconds,
            }
            for c in self._claws.values()
        ]

    def dispatch_job(
        self,
        claw_id: str,
        payload: dict[str, Any] | None = None,
        priority: ClawPriority | None = None,
    ) -> ClawJob:
        """Enqueues an execution of the given Claw into the persistent SQLite task queue."""
        claw = self._claws.get(claw_id)
        prio = priority or (claw.priority if claw else ClawPriority.NORMAL)
        max_attempts = claw.max_attempts if claw else 3
        schedule = claw.schedule if claw else None

        job = self.task_queue.enqueue(
            claw_id=claw_id,
            schedule=schedule,
            priority=prio,
            payload=payload,
            max_attempts=max_attempts,
        )
        logger.info("Dispatched Claw job %s for %s", job.job_id, claw_id)
        return job

    async def run_job_sync(
        self,
        claw_id: str,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> ClawResult:
        """Execute a Claw directly and synchronously, returning the ClawResult."""
        claw = self._claws.get(claw_id)
        if not claw:
            return ClawResult(success=False, error=f"Claw '{claw_id}' not found")

        state_dir = self.task_queue.db_path.parent
        ctx = ClawExecutionContext(
            job_id=f"job-sync-{claw_id}",
            claw_id=claw_id,
            workspace_root=self.workspace_root,
            state_dir=state_dir,
            payload=payload or {},
            _checkpoint_fn=self.task_queue.save_checkpoint,
            _notify_fn=self.notify_fn,
            _outbound_fn=self.outbound_fn,
        )

        eff_timeout = timeout or claw.timeout_seconds
        try:
            return await asyncio.wait_for(claw.run(ctx), timeout=eff_timeout)
        except asyncio.TimeoutError:
            return ClawResult(
                success=False,
                error=f"Claw execution timed out after {eff_timeout:.1f}s",
            )
        except Exception as e:
            return ClawResult(success=False, error=f"Claw execution failed: {e}")

    def cancel_job(self, job_id: str, reason: str = "User cancelled") -> bool:
        """Cancel a pending or running Claw job."""
        return self.task_queue.cancel_job(job_id, reason=reason)

    def get_job(self, job_id: str) -> ClawJob | None:
        """Retrieve a Claw job by its ID."""
        return self.task_queue.get_job(job_id)

    def start(self) -> None:
        """Start the Claws engine, background worker pool, and cron scheduler."""
        if self._running:
            return
        self._running = True
        self.worker_pool.start()
        self.cron_runner.start()
        logger.info("ClawsEngine started successfully.")

    async def stop(self) -> None:
        """Stop background worker pool and cron scheduler."""
        if not self._running:
            return
        self._running = False
        await self.worker_pool.stop()
        self.cron_runner.stop()
        logger.info("ClawsEngine stopped.")

    def get_status(self) -> dict[str, Any]:
        """Telemetry status of the Claws subsystem."""
        queue_stats = self.task_queue.get_stats()
        return {
            "running": self._running,
            "registered_claws": len(self._claws),
            "worker_concurrency": self.worker_pool.concurrency,
            "task_queue": queue_stats,
        }


_DEFAULT_CLAWS_ENGINE: ClawsEngine | None = None


def get_claws_engine() -> ClawsEngine:
    """Return the global default ClawsEngine instance."""
    global _DEFAULT_CLAWS_ENGINE
    if _DEFAULT_CLAWS_ENGINE is None:
        _DEFAULT_CLAWS_ENGINE = ClawsEngine()
    return _DEFAULT_CLAWS_ENGINE


__all__ = [
    "ClawsEngine",
    "get_claws_engine",
]
