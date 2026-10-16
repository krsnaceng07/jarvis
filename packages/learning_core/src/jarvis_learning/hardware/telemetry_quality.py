"""Telemetry quality validation and freshness policy enforcement.

Enforces INV-P10-HW-003 freshness invariant: Telemetry older than 1000ms is
classified as STALE, triggering conservative load shedding and worker pause.
"""

from __future__ import annotations

import math
import time

from jarvis_learning.hardware.models import TelemetryQuality


class TelemetryQualityValidator:
    """Validates telemetry freshness, physical bounds, and numeric integrity."""

    def __init__(self, max_freshness_ms: int = 1000) -> None:
        self.max_freshness_ms = max_freshness_ms

    def validate_temperature(
        self,
        temp_c: float | None,
        sample_timestamp_mono_ns: int,
        current_time_mono_ns: int | None = None,
    ) -> tuple[TelemetryQuality, str]:
        """Validate temperature sensor sample against physical bounds and freshness."""
        if temp_c is None:
            return TelemetryQuality.MISSING, "Sensor reported None or null"

        if math.isnan(temp_c) or math.isinf(temp_c):
            return TelemetryQuality.INVALID, "Sensor reported NaN or Infinite"

        if temp_c < -20.0 or temp_c > 140.0:
            return TelemetryQuality.OUT_OF_RANGE, f"Reading {temp_c}C outside physical bounds"

        now_ns = time.monotonic_ns() if current_time_mono_ns is None else current_time_mono_ns
        age_ms = (now_ns - sample_timestamp_mono_ns) / 1_000_000

        if age_ms > self.max_freshness_ms:
            return TelemetryQuality.STALE, f"Telemetry age {age_ms:.1f}ms exceeds 1000ms max"

        return TelemetryQuality.VALID, f"Valid reading {temp_c}C (age: {age_ms:.1f}ms)"

    def validate_memory(
        self,
        used_bytes: int | None,
        total_bytes: int | None,
        sample_timestamp_mono_ns: int,
        current_time_mono_ns: int | None = None,
    ) -> tuple[TelemetryQuality, str]:
        """Validate memory metrics against structural constraints and freshness."""
        if used_bytes is None or total_bytes is None:
            return TelemetryQuality.MISSING, "Memory telemetry is null or unavailable"

        if used_bytes < 0 or total_bytes < 0:
            return TelemetryQuality.INVALID, "Memory values cannot be negative"

        if total_bytes > 0 and used_bytes > total_bytes:
            return TelemetryQuality.INVALID, f"Used ({used_bytes}) exceeds total ({total_bytes})"

        now_ns = time.monotonic_ns() if current_time_mono_ns is None else current_time_mono_ns
        age_ms = (now_ns - sample_timestamp_mono_ns) / 1_000_000

        if age_ms > self.max_freshness_ms:
            return TelemetryQuality.STALE, f"Memory telemetry age {age_ms:.1f}ms exceeds 1000ms max"

        return TelemetryQuality.VALID, f"Valid memory telemetry (age: {age_ms:.1f}ms)"


__all__ = ["TelemetryQualityValidator"]
