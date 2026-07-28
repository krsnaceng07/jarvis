"""Reef doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReefDoctorStatus:
    healthy: bool
    detail: str = ""


def reef_doctor_contract() -> ReefDoctorStatus:
    return ReefDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
