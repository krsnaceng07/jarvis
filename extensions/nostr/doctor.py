"""Nostr doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NostrDoctorStatus:
    healthy: bool
    detail: str = ""


def nostr_doctor_contract() -> NostrDoctorStatus:
    return NostrDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
