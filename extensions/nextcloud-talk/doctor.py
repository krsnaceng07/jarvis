"""Nextcloud Talk doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NextcloudTalkDoctorStatus:
    healthy: bool
    detail: str = ""


def nextcloud_talk_doctor_contract() -> NextcloudTalkDoctorStatus:
    return NextcloudTalkDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
