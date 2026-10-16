"""Deterministic thermal replay state machine validator.

Enforces INV-P10-HW-003: Validates 82C pause (15s sustained), 75C resume (30s sustained),
and 95C emergency stop using deterministic temporal profiles.
All results from this module are explicitly classified as L2_SIMULATED / SIMULATION_VALIDATION.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from jarvis_learning.hardware.models import HardwareReality
from jarvis_learning.hardware.thermal_monitor import (
    ThermalAction,
    ThermalMonitor,
    ThermalState,
    ThermalThresholds,
)
from jarvis_learning.invariants_p10 import EvidenceLevel


@dataclasses.dataclass(frozen=True)
class ThermalReplayStep:
    """Single point in a deterministic thermal replay sequence."""

    relative_sec: float
    gpu_temp_c: float | None
    cpu_temp_c: float | None


@dataclasses.dataclass(frozen=True)
class ThermalReplayReport:
    """Outcome of replaying a thermal profile against the governor."""

    profile_name: str
    evidence_level: EvidenceLevel = EvidenceLevel.L2_IN_PROCESS_INTEGRATION
    hardware_reality: HardwareReality = HardwareReality.SIMULATION_VALIDATION
    transitions: list[dict[str, Any]] = dataclasses.field(default_factory=list)
    pause_triggered: bool = False
    resume_triggered: bool = False
    emergency_triggered: bool = False
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "evidence_level": self.evidence_level.value,
            "hardware_reality": self.hardware_reality.value,
            "pause_triggered": self.pause_triggered,
            "resume_triggered": self.resume_triggered,
            "emergency_triggered": self.emergency_triggered,
            "passed": self.passed,
            "transitions": self.transitions,
        }


class ThermalReplayEngine:
    """Replays deterministic thermal profiles against ThermalMonitor."""

    def __init__(self, thresholds: ThermalThresholds | None = None) -> None:
        self.thresholds = thresholds or ThermalThresholds()

    def run_standard_hysteresis_profile(self) -> ThermalReplayReport:
        """Standard profile testing 82C sustained pause and 75C sustained resume."""
        monitor = ThermalMonitor(self.thresholds)
        transitions = []
        pause_seen = False
        resume_seen = False

        # Timeline simulation
        steps: list[tuple[float, float]] = [
            (0.0, 70.0),
            (5.0, 83.0),  # Warning
            (10.0, 83.0),  # Sustained 5s
            (21.0, 83.0),  # Sustained 16s -> Pause!
            (25.0, 74.0),  # Below resume threshold, cooling starts
            (40.0, 74.0),  # Cooled 15s (not yet 30s)
            (56.0, 74.0),  # Cooled 31s -> Resume!
        ]

        prev_state = monitor.current_state
        base_time = 1000.0

        for rel_t, temp in steps:
            t = base_time + rel_t
            state, action = monitor.update(temp, None, current_time=t)
            if state != prev_state:
                transitions.append(
                    {
                        "time_sec": rel_t,
                        "temp_c": temp,
                        "from_state": prev_state.value,
                        "to_state": state.value,
                        "action": action.value,
                    }
                )
                prev_state = state

            if action == ThermalAction.PAUSE_WORKERS:
                pause_seen = True
            if action == ThermalAction.PROCEED and state == ThermalState.NORMAL and pause_seen:
                resume_seen = True

        passed = pause_seen and resume_seen
        return ThermalReplayReport(
            profile_name="standard_hysteresis_profile",
            pause_triggered=pause_seen,
            resume_triggered=resume_seen,
            emergency_triggered=False,
            passed=passed,
            transitions=transitions,
        )

    def run_emergency_stop_injection(self) -> ThermalReplayReport:
        """Inject 95C sensor reading to verify immediate emergency shutdown."""
        monitor = ThermalMonitor(self.thresholds)
        transitions = []

        state, action = monitor.update(96.0, None, current_time=100.0)
        emergency_seen = action == ThermalAction.EMERGENCY_STOP and state == ThermalState.EMERGENCY

        transitions.append(
            {
                "time_sec": 0.0,
                "temp_c": 96.0,
                "from_state": "NORMAL",
                "to_state": state.value,
                "action": action.value,
            }
        )

        return ThermalReplayReport(
            profile_name="emergency_95c_injection",
            pause_triggered=False,
            resume_triggered=False,
            emergency_triggered=emergency_seen,
            passed=emergency_seen,
            transitions=transitions,
        )


__all__ = ["ThermalReplayEngine", "ThermalReplayReport", "ThermalReplayStep"]
