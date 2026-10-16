"""QA Channel doctor contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QAChannelDoctorStatus:
    healthy: bool
    detail: str = ""


def qa_channel_doctor_contract() -> QAChannelDoctorStatus:
    return QAChannelDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
