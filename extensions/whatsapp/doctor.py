"""WhatsApp doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WhatsAppDoctorStatus:
    healthy: bool
    detail: str = ""


def whatsapp_doctor_contract() -> WhatsAppDoctorStatus:
    return WhatsAppDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
