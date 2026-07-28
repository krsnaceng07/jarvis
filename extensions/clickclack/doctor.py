"""ClickClack doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClickClackDoctorStatus:
    healthy: bool
    detail: str = ""


def clickclack_doctor_contract() -> ClickClackDoctorStatus:
    return ClickClackDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
