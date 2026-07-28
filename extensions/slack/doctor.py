"""Slack doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlackDoctorStatus:
    healthy: bool
    detail: str = ""


def slack_doctor_contract() -> SlackDoctorStatus:
    return SlackDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
