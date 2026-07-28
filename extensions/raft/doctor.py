"""RAFT doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RAFTDoctorStatus:
    healthy: bool
    detail: str = ""


def raft_doctor_contract() -> RAFTDoctorStatus:
    return RAFTDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
