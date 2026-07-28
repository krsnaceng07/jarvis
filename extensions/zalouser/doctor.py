"""Zalo User doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ZaloUserDoctorStatus:
    healthy: bool
    detail: str = ""


def zalouser_doctor_contract() -> ZaloUserDoctorStatus:
    return ZaloUserDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
