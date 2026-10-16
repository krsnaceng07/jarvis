"""Hardware recovery validator with baseline, peak, and post-test snapshots.

Captures state before test execution, tracks peak stress values, and validates
that memory, temperature, and device availability cleanly recover after execution.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from jarvis_learning.hardware.backend_adapters.base import BaseBackendAdapter
from jarvis_learning.hardware.models import MemoryAccounting


@dataclasses.dataclass(frozen=True)
class HardwareSnapshot:
    """Complete sensor and allocation state snapshot at a single point in time."""

    temperature_c: float | None
    memory: MemoryAccounting
    device_healthy: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature_c": self.temperature_c,
            "memory_used_bytes": self.memory.device_used_bytes,
            "memory_free_bytes": self.memory.device_free_bytes,
            "device_healthy": self.device_healthy,
        }


@dataclasses.dataclass(frozen=True)
class RecoveryAuditReport:
    """Full lifecycle recovery audit comparing baseline, peak, and post-test states."""

    baseline: HardwareSnapshot
    peak_temperature_c: float | None
    minimum_free_vram_bytes: int
    post_test: HardwareSnapshot
    memory_leaked_bytes: int
    memory_recovered: bool
    temperature_recovered: bool
    recovery_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline.to_dict(),
            "peak_temperature_c": self.peak_temperature_c,
            "minimum_free_vram_bytes": self.minimum_free_vram_bytes,
            "post_test": self.post_test.to_dict(),
            "memory_leaked_bytes": self.memory_leaked_bytes,
            "memory_recovered": self.memory_recovered,
            "temperature_recovered": self.temperature_recovered,
            "recovery_status": self.recovery_status,
        }


class RecoveryValidator:
    """Manages baseline capture, peak tracking, and recovery verification."""

    def __init__(self, adapter: BaseBackendAdapter, device_index: int = 0) -> None:
        self.adapter = adapter
        self.device_index = device_index
        self._baseline: HardwareSnapshot | None = None
        self._peak_temp: float | None = None
        self._min_free_vram: int = 0

    def capture_baseline(self) -> HardwareSnapshot:
        """Capture initial resting state before running stress or validation tests."""
        temp = self.adapter.get_temperature_c(self.device_index)
        mem = self.adapter.get_memory_accounting(self.device_index)
        healthy = self.adapter.is_available()

        self._baseline = HardwareSnapshot(
            temperature_c=temp,
            memory=mem,
            device_healthy=healthy,
        )
        self._peak_temp = temp
        self._min_free_vram = mem.device_free_bytes
        return self._baseline

    def update_peak(self, current_temp: float | None, current_free_bytes: int) -> None:
        """Update peak stress metrics observed during execution."""
        if current_temp is not None:
            if self._peak_temp is None or current_temp > self._peak_temp:
                self._peak_temp = current_temp
        if self._min_free_vram == 0 or current_free_bytes < self._min_free_vram:
            self._min_free_vram = current_free_bytes

    def evaluate_recovery(
        self,
        allowed_leak_tolerance_bytes: int = 32 * 1024 * 1024,  # 32 MB allocator cache tolerance
    ) -> RecoveryAuditReport:
        """Compare post-test resting state against pre-test baseline."""
        if self._baseline is None:
            self.capture_baseline()
            assert self._baseline is not None

        post_temp = self.adapter.get_temperature_c(self.device_index)
        post_mem = self.adapter.get_memory_accounting(self.device_index)
        post_healthy = self.adapter.is_available()

        post_snapshot = HardwareSnapshot(
            temperature_c=post_temp,
            memory=post_mem,
            device_healthy=post_healthy,
        )

        leaked_bytes = max(0, post_mem.device_used_bytes - self._baseline.memory.device_used_bytes)
        mem_recovered = leaked_bytes <= allowed_leak_tolerance_bytes

        temp_recovered = True
        if self._baseline.temperature_c is not None and post_temp is not None:
            # Temperature recovered if within 5C of baseline or under 60C
            temp_recovered = post_temp <= (self._baseline.temperature_c + 5.0) or post_temp <= 60.0

        status = "RESTORED" if (mem_recovered and temp_recovered and post_healthy) else "DEGRADED"

        return RecoveryAuditReport(
            baseline=self._baseline,
            peak_temperature_c=self._peak_temp,
            minimum_free_vram_bytes=self._min_free_vram,
            post_test=post_snapshot,
            memory_leaked_bytes=leaked_bytes,
            memory_recovered=mem_recovered,
            temperature_recovered=temp_recovered,
            recovery_status=status,
        )


__all__ = ["HardwareSnapshot", "RecoveryAuditReport", "RecoveryValidator"]
