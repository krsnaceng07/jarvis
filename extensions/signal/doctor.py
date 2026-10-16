"""Signal doctor contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignalDoctorStatus:
    healthy: bool
    detail: str = ""


def signal_doctor_contract() -> SignalDoctorStatus:
    return SignalDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
