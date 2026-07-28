"""IRC doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IRCDoctorStatus:
    """Snapshot of the IRC plugin's health."""

    healthy: bool
    detail: str = ""


def irc_doctor_contract() -> IRCDoctorStatus:
    """Return the current doctor status (Phase 5.15 stub: always healthy)."""
    return IRCDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
