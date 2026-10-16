"""Core data models, enums, and accounting structures for GPU hardware validation.

Defines strict evidence classifications, hardware reality indicators,
telemetry quality states, backend capabilities, fallback reasons, and memory accounting.
"""

from __future__ import annotations

import dataclasses
import enum

from jarvis_learning.invariants_p10 import EvidenceLevel


class HardwareReality(enum.Enum):
    """Ground truth level of hardware interaction."""

    REAL_HARDWARE = "REAL_HARDWARE"
    REAL_DRIVER = "REAL_DRIVER"
    REAL_RUNTIME = "REAL_RUNTIME"
    SIMULATION_VALIDATION = "SIMULATION_VALIDATION"
    MOCKED_FAULT_INJECTION = "MOCKED_FAULT_INJECTION"
    UNVERIFIED = "UNVERIFIED"


class TestVerdict(enum.Enum):
    """Formal outcome verdict for a hardware validation test."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    UNVERIFIED = "UNVERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SKIPPED = "SKIPPED"
    ABORTED = "ABORTED"
    DEGRADED = "DEGRADED"


class TelemetryQuality(enum.Enum):
    """Quality and freshness status of sensor readings."""

    VALID = "VALID"
    MISSING = "MISSING"
    STALE = "STALE"
    INVALID = "INVALID"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    TIMEOUT = "TIMEOUT"
    API_ERROR = "API_ERROR"
    DEVICE_REMOVED = "DEVICE_REMOVED"
    UNIT_MISMATCH = "UNIT_MISMATCH"


class DirectMLCapability(enum.Enum):
    """Graded stages of DirectML hardware and runtime support."""

    NOT_INSTALLED = "NOT_INSTALLED"
    LIBRARY_FOUND = "LIBRARY_FOUND"
    ADAPTER_ENUMERATED = "ADAPTER_ENUMERATED"
    DEVICE_CREATED = "DEVICE_CREATED"
    WORKLOAD_EXECUTED = "WORKLOAD_EXECUTED"
    MEMORY_TEST_PASSED = "MEMORY_TEST_PASSED"
    FAILURE_RECOVERY_PASSED = "FAILURE_RECOVERY_PASSED"


class FallbackReason(enum.Enum):
    """Categorized root causes for transitioning compute from GPU to host CPU."""

    FALLBACK_CUDA_UNAVAILABLE = "FALLBACK_CUDA_UNAVAILABLE"
    FALLBACK_CUDA_OOM = "FALLBACK_CUDA_OOM"
    FALLBACK_GPU_THERMAL = "FALLBACK_GPU_THERMAL"
    FALLBACK_GPU_TELEMETRY_UNSAFE = "FALLBACK_GPU_TELEMETRY_UNSAFE"
    FALLBACK_DEVICE_REMOVED = "FALLBACK_DEVICE_REMOVED"
    FALLBACK_DRIVER_ERROR = "FALLBACK_DRIVER_ERROR"
    FALLBACK_GOVERNANCE_PAUSE = "FALLBACK_GOVERNANCE_PAUSE"
    FALLBACK_MANUAL_OVERRIDE = "FALLBACK_MANUAL_OVERRIDE"


class DeviceType(enum.Enum):
    """Hardware device architecture classification."""

    DISCRETE_GPU = "DISCRETE_GPU"
    INTEGRATED_GPU = "INTEGRATED_GPU"
    CPU = "CPU"
    VIRTUAL_GPU = "VIRTUAL_GPU"
    BASIC_DISPLAY_ADAPTER = "BASIC_DISPLAY_ADAPTER"


@dataclasses.dataclass(frozen=True)
class MemoryAccounting:
    """Rigorous memory breakdown distinguishing dedicated vs shared vs process allocations."""

    total_dedicated_bytes: int
    total_shared_bytes: int
    device_used_bytes: int
    device_free_bytes: int
    process_allocated_bytes: int
    process_reserved_bytes: int
    external_usage_estimate_bytes: int
    voice_reserved_headroom_bytes: int = 1024 * 1024 * 1024  # 1 GB P0 reserve

    @property
    def usable_dedicated_vram(self) -> int:
        """Usable dedicated capacity after subtracting voice headroom reserve."""
        return max(0, self.total_dedicated_bytes - self.voice_reserved_headroom_bytes)

    @property
    def physical_usage_ratio(self) -> float:
        """Raw fraction of physical dedicated VRAM consumed."""
        if self.total_dedicated_bytes <= 0:
            return 0.0
        return min(1.0, self.device_used_bytes / self.total_dedicated_bytes)

    @property
    def governance_usage_ratio(self) -> float:
        """Effective memory pressure against usable capacity after voice reserve."""
        usable = self.usable_dedicated_vram
        if usable <= 0:
            return 1.0 if self.device_used_bytes > 0 else 0.0
        return min(1.0, self.device_used_bytes / usable)


@dataclasses.dataclass(frozen=True)
class LabSafetyLimits:
    """Strict execution boundaries preventing hardware damage or out-of-control stress."""

    max_duration_seconds: float = 60.0
    max_temperature_c: float = 80.0
    hard_abort_temperature_c: float = 85.0
    max_vram_ratio: float = 0.70
    max_allocation_bytes: int = 4 * 1024 * 1024 * 1024  # 4 GB max per probe
    sample_interval_ms: int = 250


__all__ = [
    "DeviceType",
    "DirectMLCapability",
    "EvidenceLevel",
    "FallbackReason",
    "HardwareReality",
    "LabSafetyLimits",
    "MemoryAccounting",
    "TelemetryQuality",
    "TestVerdict",
]
