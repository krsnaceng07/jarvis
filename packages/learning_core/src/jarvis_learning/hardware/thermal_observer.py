"""Real physical thermal observation and cooling curve recorder.

Performs passive and safe observation of physical device thermal behavior
over time, recording baseline, peak, and cooling curves.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Any

from jarvis_learning.hardware.backend_adapters.base import BaseBackendAdapter


@dataclasses.dataclass(frozen=True)
class ThermalObservationReport:
    """Audit report of physical thermal observation."""

    device_index: int
    sensor_available: bool
    baseline_temperature_c: float | None
    peak_temperature_c: float | None
    final_temperature_c: float | None
    cooling_rate_c_per_sec: float | None
    sample_count: int
    samples: list[tuple[float, float]]  # (relative_sec, temp_c)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_index": self.device_index,
            "sensor_available": self.sensor_available,
            "baseline_temperature_c": self.baseline_temperature_c,
            "peak_temperature_c": self.peak_temperature_c,
            "final_temperature_c": self.final_temperature_c,
            "cooling_rate_c_per_sec": self.cooling_rate_c_per_sec,
            "sample_count": self.sample_count,
            "samples": self.samples,
        }


class ThermalObserver:
    """Observes physical sensor temperatures during observation windows."""

    def __init__(self, adapter: BaseBackendAdapter) -> None:
        self.adapter = adapter

    def observe(
        self,
        device_index: int,
        duration_seconds: float = 5.0,
        interval_sec: float = 0.5,
    ) -> ThermalObservationReport:
        """Sample physical temperature over duration window."""
        start_ns = time.monotonic_ns()
        samples: list[tuple[float, float]] = []
        baseline = self.adapter.get_temperature_c(device_index)

        if baseline is None:
            return ThermalObservationReport(
                device_index=device_index,
                sensor_available=False,
                baseline_temperature_c=None,
                peak_temperature_c=None,
                final_temperature_c=None,
                cooling_rate_c_per_sec=None,
                sample_count=0,
                samples=[],
            )

        peak = baseline
        final = baseline

        while True:
            now_ns = time.monotonic_ns()
            elapsed = (now_ns - start_ns) / 1_000_000_000.0
            if elapsed > duration_seconds:
                break

            current_temp = self.adapter.get_temperature_c(device_index)
            if current_temp is not None:
                samples.append((round(elapsed, 2), current_temp))
                if current_temp > peak:
                    peak = current_temp
                final = current_temp

            time.sleep(interval_sec)

        cooling_rate = None
        if len(samples) >= 2 and samples[-1][0] > samples[0][0]:
            cooling_rate = (samples[0][1] - samples[-1][1]) / (samples[-1][0] - samples[0][0])

        return ThermalObservationReport(
            device_index=device_index,
            sensor_available=True,
            baseline_temperature_c=baseline,
            peak_temperature_c=peak,
            final_temperature_c=final,
            cooling_rate_c_per_sec=cooling_rate,
            sample_count=len(samples),
            samples=samples,
        )


__all__ = ["ThermalObservationReport", "ThermalObserver"]
