"""Deadline manager with strict hierarchical inheritance for Track 3.3.

HARD INVARIANTS:
1. Strict Inheritance Rule:
   effective_attempt_deadline = min(attempt_deadline, node_deadline, plan_deadline, task_deadline)
2. Child deadline can NEVER exceed parent deadline.
"""

from __future__ import annotations

import datetime

from jarvis_agent.scheduling.models.deadline import DeadlineContext


class DeadlineManager:
    """Evaluates deadline hierarchy and checks expiration."""

    @staticmethod
    def compute_effective_deadline(
        attempt_deadline_utc: str | None = None,
        node_deadline_utc: str | None = None,
        plan_deadline_utc: str | None = None,
        task_deadline_utc: str | None = None,
    ) -> str | None:
        """Compute the tightest deadline across the hierarchy."""
        ctx = DeadlineContext(
            task_deadline_utc=task_deadline_utc,
            plan_deadline_utc=plan_deadline_utc,
            node_deadline_utc=node_deadline_utc,
            attempt_deadline_utc=attempt_deadline_utc,
        )
        return ctx.calculate_effective_deadline()

    @staticmethod
    def is_expired(deadline_utc: str | None, now_utc: str | None = None) -> bool:
        """Check if deadline has passed."""
        if not deadline_utc:
            return False
        now_dt = (
            datetime.datetime.fromisoformat(now_utc)
            if now_utc
            else datetime.datetime.now(datetime.timezone.utc)
        )
        dl_dt = datetime.datetime.fromisoformat(deadline_utc)
        return now_dt > dl_dt


__all__ = ["DeadlineManager"]
