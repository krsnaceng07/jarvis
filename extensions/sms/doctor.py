"""SMS doctor contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SMSDoctorStatus:
    healthy: bool
    detail: str = ""


def sms_doctor_contract() -> SMSDoctorStatus:
    return SMSDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
