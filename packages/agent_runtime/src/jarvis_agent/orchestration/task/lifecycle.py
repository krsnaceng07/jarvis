"""Task lifecycle tracking, TTL monitoring, and stale task reaping."""

from __future__ import annotations

import datetime


class TaskLifecycleManager:
    """Monitors activity timestamps, enforces TTLs, and identifies stale tasks."""

    def __init__(
        self, default_ttl_seconds: float = 86400.0, default_inactivity_seconds: float = 3600.0
    ) -> None:
        self._default_ttl = default_ttl_seconds
        self._default_inactivity = default_inactivity_seconds
        self._created_at: dict[str, datetime.datetime] = {}
        self._last_active: dict[str, datetime.datetime] = {}

    def register_task(self, task_id: str, created_at: datetime.datetime | None = None) -> None:
        """Register a newly created task's birth timestamp."""
        now = created_at or datetime.datetime.now(datetime.timezone.utc)
        self._created_at[task_id] = now
        self._last_active[task_id] = now

    def touch(self, task_id: str, active_at: datetime.datetime | None = None) -> None:
        """Update last active timestamp for an ongoing task."""
        now = active_at or datetime.datetime.now(datetime.timezone.utc)
        self._last_active[task_id] = now
        if task_id not in self._created_at:
            self._created_at[task_id] = now

    def is_stale(
        self,
        task_id: str,
        inactivity_limit_seconds: float | None = None,
        ttl_limit_seconds: float | None = None,
        current_time: datetime.datetime | None = None,
    ) -> bool:
        """Determine if a task has expired based on inactivity or absolute TTL."""
        now = current_time or datetime.datetime.now(datetime.timezone.utc)
        inactivity_limit = inactivity_limit_seconds or self._default_inactivity
        ttl_limit = ttl_limit_seconds or self._default_ttl

        last = self._last_active.get(task_id)
        if last and (now - last).total_seconds() > inactivity_limit:
            return True

        created = self._created_at.get(task_id)
        if created and (now - created).total_seconds() > ttl_limit:
            return True

        return False

    def reap_stale_tasks(
        self,
        candidate_task_ids: list[str],
        inactivity_limit_seconds: float | None = None,
        current_time: datetime.datetime | None = None,
    ) -> list[str]:
        """Identify tasks that have exceeded inactivity or TTL thresholds."""
        stale: list[str] = []
        for tid in candidate_task_ids:
            if self.is_stale(
                tid, inactivity_limit_seconds=inactivity_limit_seconds, current_time=current_time
            ):
                stale.append(tid)
        return stale

    def unregister(self, task_id: str) -> None:
        """Remove lifecycle tracking for a completed or cancelled task."""
        self._created_at.pop(task_id, None)
        self._last_active.pop(task_id, None)


__all__ = ["TaskLifecycleManager"]
