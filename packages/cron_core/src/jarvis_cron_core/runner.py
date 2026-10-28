"""In-process CronRunner implementation."""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta

from .parser import ISO_TS_RE, cron_matches
from .types import CronDecl

_log = logging.getLogger("jarvis.cron_core")


class CronRunner:
    """In-process cron + one-shot scheduler.

    Created once at session start, fed every plugin's
    ``CronDecl``, then ``start()``ed in a background thread.
    ``stop()``s cleanly on shutdown.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, CronDecl] = {}
        self._last_fired: dict[str, datetime] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def add(self, job: CronDecl) -> None:
        """Register a job (idempotent by id)."""
        self._jobs[job.id] = job
        _log.info("cron: registered %s (schedule=%r)", job.id, job.schedule)

    def add_all(self, jobs: list[CronDecl]) -> None:
        for j in jobs:
            self.add(j)

    def remove(self, job_id: str) -> None:
        self._jobs.pop(job_id, None)
        self._last_fired.pop(job_id, None)

    def get(self, job_id: str) -> CronDecl | None:
        """Lookup a registered job by id."""
        return self._jobs.get(job_id)

    def list(self) -> list[CronDecl]:
        return list(self._jobs.values())

    def start(self, *, tick_seconds: float = 30.0) -> None:
        """Start the runner in a background thread.

        ``tick_seconds`` is the poll interval. 30s is a good default.
        """
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(tick_seconds,), daemon=True, name="cron-runner"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self, tick_seconds: float) -> None:
        # Private event loop so plugin handlers (which are
        # declared ``async``) can be awaited cleanly.
        self._loop = asyncio.new_event_loop()
        try:
            while not self._stop.is_set():
                self._tick()
                self._stop.wait(tick_seconds)
        finally:
            self._loop.close()
            self._loop = None

    def _tick(self) -> None:
        """Evaluate every job once. Fire any that are due."""
        now = datetime.now()
        for job_id, job in list(self._jobs.items()):
            if not job.enabled:
                continue
            try:
                due = self._is_due(job, now)
            except Exception as e:
                _log.warning("cron: %s schedule error: %s", job_id, e)
                continue
            if not due:
                continue
            last = self._last_fired.get(job_id)
            if last and (now - last) < timedelta(seconds=30):
                # Debounce: don't fire twice within 30s.
                continue
            self._last_fired[job_id] = now
            self._fire(job)

            # Auto-retire one-shot ISO timestamp jobs after successful firing
            if ISO_TS_RE.match(job.schedule):
                self._jobs.pop(job_id, None)
                try:
                    from extensions.cron.runtime import CronTable

                    CronTable.default().remove(job_id)
                except Exception:
                    pass

    def _is_due(self, job: CronDecl, now: datetime) -> bool:
        """Return True if ``job`` should fire at ``now``."""
        if ISO_TS_RE.match(job.schedule):
            try:
                raw_ts = job.schedule.replace("Z", "+00:00")
                target = datetime.fromisoformat(raw_ts)
                if target.tzinfo is not None and now.tzinfo is None:
                    from datetime import timezone

                    now_cmp = datetime.now(timezone.utc)
                elif target.tzinfo is None and now.tzinfo is not None:
                    now_cmp = now.replace(tzinfo=None)
                else:
                    now_cmp = now
            except ValueError as e:
                raise ValueError(f"invalid ISO timestamp: {job.schedule!r}") from e
            return now_cmp >= target
        # Cron expression — evaluate minute-level match.
        return cron_matches(job.schedule, now)

    def _fire(self, job: CronDecl) -> None:
        """Invoke the job's handler (async-safe)."""
        _log.info("cron: firing %s", job.id)
        try:
            result = job.handler()
        except Exception as e:
            _log.warning("cron: %s handler raised: %s", job.id, e)
            return
        if asyncio.iscoroutine(result):
            try:
                # If running on the dedicated cron-runner thread, execute directly on self._loop
                if self._loop is not None and threading.current_thread() == self._thread:
                    self._loop.run_until_complete(asyncio.wait_for(result, timeout=30.0))
                elif self._loop is not None and self._loop.is_running():
                    fut = asyncio.run_coroutine_threadsafe(result, self._loop)
                    fut.result(timeout=30.0)
                else:
                    asyncio.run(asyncio.wait_for(result, timeout=30.0))
            except Exception as e:
                _log.warning("cron: %s async handler failed: %s", job.id, e)

    def run_job(self, job_id: str) -> bool:
        """Trigger an immediate run of a registered job by id."""
        job = self.get(job_id)
        if job is None:
            return False
        self._fire(job)
        self._last_fired[job.id] = datetime.now()
        return True


_DEFAULT_CRON_RUNNER: CronRunner | None = None


def get_default_cron_runner() -> CronRunner:
    """Return the global default in-process CronRunner instance."""
    global _DEFAULT_CRON_RUNNER
    if _DEFAULT_CRON_RUNNER is None:
        _DEFAULT_CRON_RUNNER = CronRunner()
    return _DEFAULT_CRON_RUNNER


__all__ = ["CronRunner", "get_default_cron_runner"]
