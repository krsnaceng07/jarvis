"""Independent reference oracle for hardware governor state transitions.

Provides an isolated, mathematically independent ground-truth oracle for
VRAM threshold evaluation and thermal hysteresis without importing production governor code.
"""

from __future__ import annotations


class GovernanceReferenceModel:
    """Independent oracle for evaluating expected governor states and actions."""

    @staticmethod
    def evaluate_vram_reference(
        utilization_pct: float,
        free_bytes: int,
        total_bytes: int,
        reserved_headroom_bytes: int = 1024 * 1024 * 1024,
    ) -> tuple[str, str]:
        """Independent reference calculation for VRAM governor response.

        Returns (expected_state, expected_action).
        """
        # 1. Check emergency limit (92%)
        if utilization_pct >= 0.92:
            return "EMERGENCY_EXCEEDED", "EMERGENCY_SUSPEND"

        # 2. Check hard limit (85%)
        if utilization_pct >= 0.85:
            return "HARD_EXCEEDED", "PAUSE_EVALUATION"

        # 3. Check soft limit (75%)
        if utilization_pct >= 0.75:
            return "SOFT_EXCEEDED", "TRIGGER_GC"

        # 4. Check active headroom reservation
        if total_bytes > 0 and free_bytes < reserved_headroom_bytes:
            return "HARD_EXCEEDED", "PAUSE_EVALUATION"

        return "NORMAL", "PROCEED"

    @staticmethod
    def evaluate_thermal_reference(
        eff_temp_c: float | None,
        duration_sustained_sec: float,
    ) -> tuple[str, str]:
        """Independent reference calculation for thermal monitor response.

        Returns (expected_state, expected_action).
        """
        if eff_temp_c is None:
            return "SENSOR_UNAVAILABLE", "PAUSE_WORKERS"

        if eff_temp_c >= 95.0:
            return "EMERGENCY", "EMERGENCY_STOP"

        if eff_temp_c >= 82.0:
            if duration_sustained_sec >= 15.0:
                return "THROTTLED", "PAUSE_WORKERS"
            return "WARNING", "PROCEED"

        return "NORMAL", "PROCEED"


__all__ = ["GovernanceReferenceModel"]
