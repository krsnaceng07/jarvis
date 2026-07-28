"""iMessage doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class iMessageDoctorStatus:
    """Snapshot of the iMessage plugin's health."""

    healthy: bool
    detail: str = ""


def imessage_doctor_contract() -> iMessageDoctorStatus:
    """Return the current doctor status (Phase 5.15 stub: always healthy)."""
    return iMessageDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
