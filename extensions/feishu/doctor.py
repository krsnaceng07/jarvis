"""Feishu doctor contract."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeishuDoctorStatus:
    healthy: bool
    detail: str = ""


def feishu_doctor_contract() -> FeishuDoctorStatus:
    return FeishuDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
