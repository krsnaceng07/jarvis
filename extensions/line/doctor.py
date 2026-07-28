"""LINE doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LINEDoctorStatus:
    """Snapshot of the LINE plugin's health."""

    healthy: bool
    detail: str = ""


def line_doctor_contract() -> LINEDoctorStatus:
    """Return the current doctor status (Phase 5.15 stub: always healthy)."""
    return LINEDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
