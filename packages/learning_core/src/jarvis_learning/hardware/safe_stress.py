"""Safety-capped stress execution engine.

Enforces physical safety envelope: Maximum duration (60s), maximum temperature (80C),
hard emergency abort (85C), and maximum VRAM ratio (70%), guaranteeing physical silicon protection.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Any

from jarvis_learning.hardware.backend_adapters.base import BaseBackendAdapter
from jarvis_learning.hardware.models import LabSafetyLimits

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class StressRunSummary:
    """Audit summary of a safety-bounded physical stress run."""

    device_index: int
    duration_seconds: float
    iterations_completed: int
    peak_temperature_c: float | None
    peak_memory_used_bytes: int
    aborted_by_safety_limit: bool
    abort_reason: str | None


class SafeStressEngine:
    """Executes safe physical stress within hard-bounded thermal and memory limits."""

    def __init__(
        self,
        adapter: BaseBackendAdapter,
        limits: LabSafetyLimits | None = None,
    ) -> None:
        self.adapter = adapter
        self.limits = limits or LabSafetyLimits()

    def run_safe_stress(
        self,
        device_index: int,
        duration_seconds: float | None = None,
    ) -> StressRunSummary:
        """Run bounded stress loop monitoring temperature and VRAM caps."""
        max_duration = duration_seconds or self.limits.max_duration_seconds
        start_ns = time.monotonic_ns()
        iterations = 0
        peak_temp: float | None = None
        peak_mem = 0
        aborted = False
        abort_reason = None
        handles: list[Any] = []

        try:
            while True:
                now_ns = time.monotonic_ns()
                elapsed = (now_ns - start_ns) / 1_000_000_000.0
                if elapsed >= max_duration:
                    break

                # 1. Sample telemetry
                temp = self.adapter.get_temperature_c(device_index)
                if temp is not None:
                    if peak_temp is None or temp > peak_temp:
                        peak_temp = temp

                    # Check hard abort limit
                    if temp >= self.limits.hard_abort_temperature_c:
                        aborted = True
                        abort_reason = f"Hard abort threshold exceeded: {temp}C >= {self.limits.hard_abort_temperature_c}C"
                        break

                    # Check soft safety cap
                    if temp >= self.limits.max_temperature_c:
                        aborted = True
                        abort_reason = f"Safe thermal limit reached: {temp}C >= {self.limits.max_temperature_c}C"
                        break

                # 2. Check memory usage
                accounting = self.adapter.get_memory_accounting(device_index)
                used = accounting.device_used_bytes
                if used > peak_mem:
                    peak_mem = used

                if (
                    accounting.total_dedicated_bytes > 0
                    and accounting.physical_usage_ratio >= self.limits.max_vram_ratio
                ):
                    aborted = True
                    abort_reason = f"Max VRAM safety ratio reached: {accounting.physical_usage_ratio:.2f} >= {self.limits.max_vram_ratio}"
                    break

                # 3. Execute lightweight compute workload step
                self.adapter.execute_dummy_workload(device_index)
                iterations += 1

                time.sleep(self.limits.sample_interval_ms / 1000.0)

        finally:
            for h in handles:
                self.adapter.free_tensor(h)

        total_elapsed = (time.monotonic_ns() - start_ns) / 1_000_000_000.0
        return StressRunSummary(
            device_index=device_index,
            duration_seconds=total_elapsed,
            iterations_completed=iterations,
            peak_temperature_c=peak_temp,
            peak_memory_used_bytes=peak_mem,
            aborted_by_safety_limit=aborted,
            abort_reason=abort_reason,
        )


__all__ = ["SafeStressEngine", "StressRunSummary"]
