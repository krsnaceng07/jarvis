"""Matrix doctor contract."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MatrixDoctorStatus:
    healthy: bool
    detail: str = ""


def matrix_doctor_contract() -> MatrixDoctorStatus:
    return MatrixDoctorStatus(
        healthy=True,
        detail="Phase 5.15 stub — no real health checks yet",
    )
