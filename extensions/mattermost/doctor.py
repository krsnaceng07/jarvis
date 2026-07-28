"""Mattermost doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MattermostDoctorStatus:
    healthy: bool
    detail: str = ""


def mattermost_doctor_contract() -> MattermostDoctorStatus:
    return MattermostDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
