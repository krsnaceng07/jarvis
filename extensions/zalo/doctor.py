"""Zalo doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ZaloDoctorStatus:
    """Snapshot of the Zalo plugin's health."""

    healthy: bool
    detail: str = ""


def zalo_doctor_contract() -> ZaloDoctorStatus:
    """Return the current doctor status (Phase 5.15 stub: always healthy)."""
    return ZaloDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
