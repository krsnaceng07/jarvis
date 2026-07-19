"""Cron runner — cross-platform scheduled jobs.

Mirrors OpenClaw's ``src/cron/`` system. A plugin registers a
``CronDecl`` (id, schedule, handler) via ``api.register_cron(...)``.
The ``CronRunner`` evaluates the schedule every tick and invokes
the handler when it's time.

Phase 2 uses a simple in-process loop (no APScheduler dependency).
Each job's ``schedule`` is either:

  - A 5-field cron expression (``"*/5 * * * *"``) — supports
    ``*``, ``*/N``, ranges (``1-5``), and lists (``1,3,5``).
  - An ISO timestamp (``"2026-07-20T09:00:00"``) for one-shots.

For real production use, swap this for ``APScheduler`` or
``croniter`` (the user's preference). The shape is identical.

Also note: this replaces the Windows-only ``schtasks`` path in
``extensions/tool_reminder/plugin.py``. The reminder plugin in
Phase 2 uses the cron runner so reminders work on all 3 OSes.
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
from datetime import datetime, timedelta
from typing import Any

from jarvis_sdk import CronDecl


_log = logging.getLogger("jarvis.cron")

# ISO timestamp pattern (one-shot jobs).
_ISO_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


class CronRunner:
    """In-process cron + one-shot scheduler.

    Phase 2 host. Created once at session start, fed every plugin's
    ``CronDecl`` from ``_load_plugins()``, then ``start()``ed in a
    background thread. ``stop()``s cleanly on shutdown.
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

    def list(self) -> list[CronDecl]:
        return list(self._jobs.values())

    def start(self, *, tick_seconds: float = 30.0) -> None:
        """Start the runner in a background thread.

        ``tick_seconds`` is the poll interval. 30s is a good default
        (the operator doesn't expect minute-level precision on a
        desktop AI; we can tighten when we have a real scheduler).
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
        # We run a private event loop so plugin handlers (which are
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
            except Exception as e:  # noqa: BLE001
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

    def _is_due(self, job: CronDecl, now: datetime) -> bool:
        """Return True if ``job`` should fire at ``now``."""
        if _ISO_TS_RE.match(job.schedule):
            try:
                target = datetime.fromisoformat(job.schedule)
            except ValueError as e:
                raise ValueError(f"invalid ISO timestamp: {job.schedule!r}") from e
            return now >= target
        # Cron expression — evaluate minute-level match.
        return _cron_matches(job.schedule, now)

    def _fire(self, job: CronDecl) -> None:
        """Invoke the job's handler (async-safe)."""
        _log.info("cron: firing %s", job.id)
        try:
            result = job.handler()
        except Exception as e:  # noqa: BLE001
            _log.warning("cron: %s handler raised: %s", job.id, e)
            return
        if asyncio.iscoroutine(result) and self._loop is not None:
            try:
                fut = asyncio.run_coroutine_threadsafe(result, self._loop)
                fut.result(timeout=30.0)
            except Exception as e:  # noqa: BLE001
                _log.warning("cron: %s async handler failed: %s", job.id, e)


# ── Tiny cron-expression evaluator ─────────────────────────────────
# Supports the common subset: *, */N, ranges (1-5), lists (1,3,5).
# Field order: minute hour day-of-month month day-of-week.


def _cron_matches(expr: str, when: datetime) -> bool:
    """Return True if ``when`` matches the 5-field cron expression."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            f"cron expression must have 5 fields (minute hour dom mon dow); "
            f"got {len(fields)}: {expr!r}"
        )
    minute, hour, dom, mon, dow = fields
    return (
        _field_matches(minute, when.minute, 0, 59)
        and _field_matches(hour, when.hour, 0, 23)
        and _field_matches(dom, when.day, 1, 31)
        and _field_matches(mon, when.month, 1, 12)
        and _field_matches(dow, when.weekday(), 0, 6)  # Mon=0, Sun=6
    )


def _field_matches(spec: str, value: int, lo: int, hi: int) -> bool:
    """Return True if a single cron field matches ``value``."""
    for part in spec.split(","):
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = max(1, int(step_str))
        else:
            base = part
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            s, e = base.split("-", 1)
            start, end = int(s), int(e)
        else:
            start = end = int(base)
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


__all__ = ["CronRunner"]
