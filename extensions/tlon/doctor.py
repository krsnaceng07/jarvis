"""Tlon doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TlonDoctorStatus:
    healthy: bool
    detail: str = ""


def tlon_doctor_contract() -> TlonDoctorStatus:
    return TlonDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
