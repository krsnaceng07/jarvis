"""Synology Chat doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SynologyChatDoctorStatus:
    """Snapshot of the Synology Chat plugin's health."""

    healthy: bool
    detail: str = ""


def synology_chat_doctor_contract() -> SynologyChatDoctorStatus:
    """Return the current doctor status (Phase 5.15 stub: always healthy)."""
    return SynologyChatDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
