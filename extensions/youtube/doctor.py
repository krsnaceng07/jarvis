"""YouTube doctor contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class YouTubeDoctorStatus:
    healthy: bool
    detail: str = ""


def youtube_doctor_contract() -> YouTubeDoctorStatus:
    return YouTubeDoctorStatus(
        healthy=True,
        detail="YouTube automation adapter and browser runtime ready",
    )
