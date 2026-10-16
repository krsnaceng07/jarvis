"""Detached operator dashboard sidecar service.

Enforces INV-P10-OPS-001: Operator dashboard unavailability must not block,
pause, or alter active runtime or learning workers.
"""

from __future__ import annotations

import dataclasses
import logging

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class DashboardSnapshot:
    """Read-only snapshot of system operational metrics."""

    timestamp_ns: int
    queue_depth: int
    active_worker_count: int
    total_events_processed: int
    active_model_id: str
    active_model_version: str
    recent_alerts: list[str] = dataclasses.field(default_factory=list)


class DashboardSidecarService:
    """Detached sidecar service presenting operator observability without runtime coupling."""

    def __init__(self) -> None:
        self._is_running = False

    def start(self) -> None:
        self._is_running = True

    def stop(self) -> None:
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def collect_snapshot(
        self,
        queue_depth: int,
        worker_count: int,
        events_processed: int,
        model_id: str,
        model_version: str,
        alerts: list[str] | None = None,
    ) -> DashboardSnapshot:
        """Collect read-only metrics snapshot."""
        import time

        return DashboardSnapshot(
            timestamp_ns=time.time_ns(),
            queue_depth=queue_depth,
            active_worker_count=worker_count,
            total_events_processed=events_processed,
            active_model_id=model_id,
            active_model_version=model_version,
            recent_alerts=alerts or [],
        )

    def simulate_failure(self) -> None:
        """Simulate unexpected dashboard sidecar crash."""
        self._is_running = False
        raise RuntimeError("DASHBOARD_CRASHED: Out of memory or network disconnect")
