"""Hardware telemetry collector and raw sample accumulator.

Maintains monotonic time series of temperature, memory, utilization, and power
with explicit telemetry quality and provenance annotations.
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from typing import Any

from jarvis_learning.hardware.models import MemoryAccounting, TelemetryQuality
from jarvis_learning.hardware.telemetry_quality import TelemetryQualityValidator


@dataclasses.dataclass(frozen=True)
class HardwareTelemetrySample:
    """Individual time-stamped sensor snapshot for an individual device."""

    sample_id: int
    device_index: int
    timestamp_mono_ns: int
    timestamp_utc: str
    temperature_c: float | None
    temperature_quality: TelemetryQuality
    temperature_reason: str
    memory: MemoryAccounting
    memory_quality: TelemetryQuality
    memory_reason: str
    gpu_utilization_pct: float | None
    power_watts: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "device_index": self.device_index,
            "timestamp_mono_ns": self.timestamp_mono_ns,
            "timestamp_utc": self.timestamp_utc,
            "temperature_c": self.temperature_c,
            "temperature_quality": self.temperature_quality.value,
            "temperature_reason": self.temperature_reason,
            "memory": {
                "total_dedicated_bytes": self.memory.total_dedicated_bytes,
                "total_shared_bytes": self.memory.total_shared_bytes,
                "device_used_bytes": self.memory.device_used_bytes,
                "device_free_bytes": self.memory.device_free_bytes,
                "process_allocated_bytes": self.memory.process_allocated_bytes,
                "process_reserved_bytes": self.memory.process_reserved_bytes,
                "external_usage_estimate_bytes": self.memory.external_usage_estimate_bytes,
                "voice_reserved_headroom_bytes": self.memory.voice_reserved_headroom_bytes,
                "physical_usage_ratio": self.memory.physical_usage_ratio,
                "governance_usage_ratio": self.memory.governance_usage_ratio,
            },
            "memory_quality": self.memory_quality.value,
            "memory_reason": self.memory_reason,
            "gpu_utilization_pct": self.gpu_utilization_pct,
            "power_watts": self.power_watts,
        }


class TelemetryCollector:
    """Collects and audits hardware telemetry samples over time."""

    def __init__(self, validator: TelemetryQualityValidator | None = None) -> None:
        self.validator = validator or TelemetryQualityValidator(max_freshness_ms=1000)
        self._samples: list[HardwareTelemetrySample] = []
        self._sample_counter = 0

    @property
    def samples(self) -> list[HardwareTelemetrySample]:
        return list(self._samples)

    def record_sample(
        self,
        device_index: int,
        temperature_c: float | None,
        memory: MemoryAccounting,
        gpu_utilization_pct: float | None = None,
        power_watts: float | None = None,
        timestamp_mono_ns: int | None = None,
        evaluation_mono_ns: int | None = None,
    ) -> HardwareTelemetrySample:
        """Capture and validate an individual telemetry snapshot."""
        now_mono = time.monotonic_ns() if timestamp_mono_ns is None else timestamp_mono_ns
        eval_mono = now_mono if evaluation_mono_ns is None else evaluation_mono_ns
        utc_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        t_quality, t_reason = self.validator.validate_temperature(
            temperature_c, now_mono, eval_mono
        )
        m_quality, m_reason = self.validator.validate_memory(
            memory.device_used_bytes, memory.total_dedicated_bytes, now_mono, eval_mono
        )

        self._sample_counter += 1
        sample = HardwareTelemetrySample(
            sample_id=self._sample_counter,
            device_index=device_index,
            timestamp_mono_ns=now_mono,
            timestamp_utc=utc_str,
            temperature_c=temperature_c,
            temperature_quality=t_quality,
            temperature_reason=t_reason,
            memory=memory,
            memory_quality=m_quality,
            memory_reason=m_reason,
            gpu_utilization_pct=gpu_utilization_pct,
            power_watts=power_watts,
        )
        self._samples.append(sample)
        return sample


__all__ = ["HardwareTelemetrySample", "TelemetryCollector"]
