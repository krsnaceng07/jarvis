"""QQ Bot doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QQBotDoctorStatus:
    """Snapshot of the QQ Bot plugin's health."""

    healthy: bool
    detail: str = ""


def qqbot_doctor_contract() -> QQBotDoctorStatus:
    """Return the current doctor status (Phase 5.15 stub: always healthy)."""
    return QQBotDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
