"""Deadline hierarchy and effective inheritance calculation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class DeadlineContext:
    """Encapsulates hierarchical deadlines from task down to individual attempt."""

    task_deadline_utc: str | None = None
    plan_deadline_utc: str | None = None
    node_deadline_utc: str | None = None
    attempt_deadline_utc: str | None = None

    def calculate_effective_deadline(self) -> str | None:
        """Derive effective_attempt_deadline = min(attempt, node, plan, task)."""
        valid_dts: list[datetime.datetime] = []
        for dl in (
            self.attempt_deadline_utc,
            self.node_deadline_utc,
            self.plan_deadline_utc,
            self.task_deadline_utc,
        ):
            if dl:
                try:
                    valid_dts.append(datetime.datetime.fromisoformat(dl))
                except Exception:
                    pass
        if not valid_dts:
            return None
        min_dt = min(valid_dts)
        return min_dt.isoformat()

    def is_expired(self, current_time_utc: str | None = None) -> bool:
        """True if current time exceeds the effective deadline."""
        eff = self.calculate_effective_deadline()
        if not eff:
            return False
        now_dt = (
            datetime.datetime.fromisoformat(current_time_utc)
            if current_time_utc
            else datetime.datetime.now(datetime.timezone.utc)
        )
        eff_dt = datetime.datetime.fromisoformat(eff)
        return now_dt > eff_dt

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = ["DeadlineContext"]
