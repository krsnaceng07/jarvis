"""Google Chat doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GoogleChatDoctorStatus:
    healthy: bool
    detail: str = ""


def googlechat_doctor_contract() -> GoogleChatDoctorStatus:
    return GoogleChatDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
