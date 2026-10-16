"""Thermal monitoring with hysteresis and sustained observation duration.

Enforces INV-P10-HW-003: Thermal throttling must use hysteresis (>=82C pause,
<=75C resume) and sustained observation duration.
"""

from __future__ import annotations

import dataclasses
import enum
import time


class ThermalState(enum.Enum):
    """Graded thermal health state."""

    NORMAL = "NORMAL"
    WARNING = "WARNING"
    THROTTLED = "THROTTLED"
    EMERGENCY = "EMERGENCY"
    SENSOR_UNAVAILABLE = "SENSOR_UNAVAILABLE"


class ThermalAction(enum.Enum):
    """Prescribed thermal response."""

    PROCEED = "PROCEED"
    PAUSE_WORKERS = "PAUSE_WORKERS"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclasses.dataclass(frozen=True)
class ThermalThresholds:
    """Configurable thermal parameters with hysteresis."""

    gpu_pause_c: float = 82.0
    gpu_resume_c: float = 75.0
    cpu_pause_c: float = 85.0
    cpu_resume_c: float = 78.0
    sustained_pause_sec: float = 15.0
    sustained_resume_sec: float = 30.0


class ThermalMonitor:
    """Monitors device temperatures and enforces hysteresis-gated throttling."""

    def __init__(self, thresholds: ThermalThresholds | None = None) -> None:
        self._thresholds = thresholds or ThermalThresholds()
        self._state = ThermalState.NORMAL
        self._high_temp_start: float | None = None
        self._cool_temp_start: float | None = None

    @property
    def current_state(self) -> ThermalState:
        return self._state

    def update(
        self,
        gpu_temp_c: float | None,
        cpu_temp_c: float | None,
        current_time: float | None = None,
    ) -> tuple[ThermalState, ThermalAction]:
        """Update thermal monitor with latest sensor readings."""
        now = time.time() if current_time is None else current_time

        # Fail conservative if sensors unavailable
        if gpu_temp_c is None and cpu_temp_c is None:
            self._state = ThermalState.SENSOR_UNAVAILABLE
            return ThermalState.SENSOR_UNAVAILABLE, ThermalAction.PAUSE_WORKERS

        # Determine effective maximum temperatures
        eff_gpu = gpu_temp_c if gpu_temp_c is not None else 0.0
        eff_cpu = cpu_temp_c if cpu_temp_c is not None else 0.0

        # Check emergency limit (> 95C)
        if eff_gpu >= 95.0 or eff_cpu >= 95.0:
            self._state = ThermalState.EMERGENCY
            return ThermalState.EMERGENCY, ThermalAction.EMERGENCY_STOP

        is_over_threshold = (
            eff_gpu >= self._thresholds.gpu_pause_c or eff_cpu >= self._thresholds.cpu_pause_c
        )

        is_below_resume = (
            eff_gpu <= self._thresholds.gpu_resume_c and eff_cpu <= self._thresholds.cpu_resume_c
        )

        if self._state in (ThermalState.NORMAL, ThermalState.WARNING):
            if is_over_threshold:
                if self._high_temp_start is None:
                    self._high_temp_start = now
                    self._state = ThermalState.WARNING
                elif now - self._high_temp_start >= self._thresholds.sustained_pause_sec:
                    self._state = ThermalState.THROTTLED
                    self._cool_temp_start = None
                    return ThermalState.THROTTLED, ThermalAction.PAUSE_WORKERS
            else:
                self._high_temp_start = None
                self._state = ThermalState.NORMAL

            action = (
                ThermalAction.PAUSE_WORKERS
                if self._state == ThermalState.THROTTLED
                else ThermalAction.PROCEED
            )
            return self._state, action

        elif self._state == ThermalState.THROTTLED:
            # Must remain below resume threshold for sustained duration to recover
            if is_below_resume:
                if self._cool_temp_start is None:
                    self._cool_temp_start = now
                elif now - self._cool_temp_start >= self._thresholds.sustained_resume_sec:
                    self._state = ThermalState.NORMAL
                    self._high_temp_start = None
                    self._cool_temp_start = None
                    return ThermalState.NORMAL, ThermalAction.PROCEED
            else:
                # Reset cooling timer if temperature spiked back up
                self._cool_temp_start = None

            return ThermalState.THROTTLED, ThermalAction.PAUSE_WORKERS

        return self._state, ThermalAction.PAUSE_WORKERS
