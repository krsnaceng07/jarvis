"""Twitch doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TwitchDoctorStatus:
    """Snapshot of the Twitch plugin's health."""

    healthy: bool
    detail: str = ""


def twitch_doctor_contract() -> TwitchDoctorStatus:
    """Return the current doctor status (Phase 5.15 stub: always healthy)."""
    return TwitchDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
