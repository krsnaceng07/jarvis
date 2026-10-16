"""Dynamic VRAM Governor with 3-tier thresholds and active runtime headroom reservation.

Enforces INV-P10-HW-002: Resource governors must reserve guaranteed capacity
and headroom for the active JARVIS runtime.
"""

from __future__ import annotations

import dataclasses
import enum


class VRAMState(enum.Enum):
    """Graded levels of memory pressure."""

    NORMAL = "NORMAL"
    SOFT_EXCEEDED = "SOFT_EXCEEDED"
    HARD_EXCEEDED = "HARD_EXCEEDED"
    EMERGENCY_EXCEEDED = "EMERGENCY_EXCEEDED"


class VRAMAction(enum.Enum):
    """Prescribed governor response action."""

    PROCEED = "PROCEED"
    TRIGGER_GC = "TRIGGER_GC"
    PAUSE_EVALUATION = "PAUSE_EVALUATION"
    EMERGENCY_SUSPEND = "EMERGENCY_SUSPEND"


@dataclasses.dataclass(frozen=True)
class VRAMThresholds:
    """Configurable memory governor limits."""

    soft_limit_pct: float = 0.75
    hard_limit_pct: float = 0.85
    emergency_limit_pct: float = 0.92
    reserved_runtime_bytes: int = 1024 * 1024 * 1024  # 1 GB reserved for active JARVIS runtime


@dataclasses.dataclass(frozen=True)
class VRAMMetrics:
    """Snapshot of device memory allocation."""

    total_bytes: int
    allocated_bytes: int
    reserved_bytes: int
    free_bytes: int
    peak_bytes: int
    fragmentation_estimate: float = 0.0

    @property
    def utilization_pct(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return self.allocated_bytes / self.total_bytes


class VRAMGovernor:
    """Enforces VRAM limits and triggers load-shedding and worker suspensions."""

    def __init__(self, thresholds: VRAMThresholds | None = None) -> None:
        self._thresholds = thresholds or VRAMThresholds()

    @property
    def thresholds(self) -> VRAMThresholds:
        return self._thresholds

    def evaluate(self, metrics: VRAMMetrics) -> tuple[VRAMState, VRAMAction]:
        """Evaluate memory metrics against 3-tier thresholds and active headroom."""
        util = metrics.utilization_pct

        # Check emergency ceiling first
        if util >= self._thresholds.emergency_limit_pct:
            return VRAMState.EMERGENCY_EXCEEDED, VRAMAction.EMERGENCY_SUSPEND

        # Check hard limit
        if util >= self._thresholds.hard_limit_pct:
            return VRAMState.HARD_EXCEEDED, VRAMAction.PAUSE_EVALUATION

        # Check soft limit
        if util >= self._thresholds.soft_limit_pct:
            return VRAMState.SOFT_EXCEEDED, VRAMAction.TRIGGER_GC

        # Check headroom reservation: free memory must be >= reserved_runtime_bytes
        if metrics.free_bytes < self._thresholds.reserved_runtime_bytes and metrics.total_bytes > 0:
            # Free memory insufficient for active assistant headroom
            return VRAMState.HARD_EXCEEDED, VRAMAction.PAUSE_EVALUATION

        return VRAMState.NORMAL, VRAMAction.PROCEED
