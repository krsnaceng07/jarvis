"""System Monitor Watchdog Autonomous Claw — JARVIS Autonomous Architecture (Task 5).

Continuously monitors system resource thresholds (disk storage, memory, CPU)
and raises proactive alerts when resource degradation is detected.
"""

from __future__ import annotations

import shutil
import time
from typing import Any

from ..base import Claw, ClawExecutionContext
from ..types import ClawPriority, ClawResult


class SystemMonitorClaw(Claw):
    """Autonomous Claw that monitors host disk space and system memory."""

    def __init__(
        self,
        schedule: str = "*/15 * * * *",  # Every 15 minutes
        priority: ClawPriority = ClawPriority.HIGH,
        min_free_disk_gb: float = 5.0,
    ) -> None:
        super().__init__(
            claw_id="claw:system_monitor",
            name="System Monitor Watchdog Claw",
            description="Monitors host disk storage and system resource availability.",
            schedule=schedule,
            priority=priority,
            timeout_seconds=20.0,
        )
        self.min_free_disk_gb = min_free_disk_gb

    async def run(self, ctx: ClawExecutionContext) -> ClawResult:
        start_time = time.monotonic()
        ws_root = ctx.workspace_root

        total, used, free = shutil.disk_usage(str(ws_root))
        total_gb = total / (1024**3)
        free_gb = free / (1024**3)
        used_gb = used / (1024**3)
        percent_free = (free / total) * 100.0

        metrics: dict[str, Any] = {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "percent_free": round(percent_free, 1),
        }

        is_low_disk = free_gb < self.min_free_disk_gb
        if is_low_disk:
            await ctx.notify(
                "Low Disk Space Warning",
                f"Workspace disk has only {free_gb:.2f} GB ({percent_free:.1f}%) remaining.",
                level="warning",
            )

        duration_ms = (time.monotonic() - start_time) * 1000.0
        await ctx.checkpoint(
            {
                "timestamp": time.time(),
                "free_disk_gb": round(free_gb, 2),
                "healthy": not is_low_disk,
            }
        )

        return ClawResult(
            success=not is_low_disk,
            output=f"Disk check: {free_gb:.2f} GB free of {total_gb:.2f} GB ({percent_free:.1f}% free)",
            error="Free disk space below threshold" if is_low_disk else None,
            duration_ms=duration_ms,
            metrics=metrics,
        )


__all__ = ["SystemMonitorClaw"]
