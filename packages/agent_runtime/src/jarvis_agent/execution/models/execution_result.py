"""ExecutionStatus enum and authoritative ExecutionResult model for Track 3.2.

Captures the empirical outcome of command execution, including runtime duration,
adapter output, observation records, independent verification results, cryptographic
evidence references, and sandbox isolation levels used.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
import enum
from typing import Any

from jarvis_agent.orchestration.models.observation import ObservationRecord
from jarvis_agent.orchestration.models.verification import VerificationResult


class ExecutionStatus(enum.Enum):
    """Lifecycle and terminal execution status codes."""

    ADMITTED = "ADMITTED"
    DISPATCHED = "DISPATCHED"
    STARTED = "STARTED"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    SUCCEEDED_PENDING_VERIFICATION = "SUCCEEDED_PENDING_VERIFICATION"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    AMBIGUOUS = "AMBIGUOUS"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"

    @property
    def is_terminal(self) -> bool:
        """Return True if execution has reached a terminal state."""
        return self in (
            ExecutionStatus.CANCELLED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMED_OUT,
            ExecutionStatus.AMBIGUOUS,
            ExecutionStatus.VERIFIED,
            ExecutionStatus.VERIFICATION_FAILED,
        )


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Authoritative result produced by Track 3.2 execution runtime."""

    execution_id: str
    command_id: str
    task_id: str
    plan_id: str
    plan_revision: int
    node_id: str
    attempt_id: int
    status: ExecutionStatus
    failure_class: str | None = None
    started_at_utc: str = ""
    completed_at_utc: str = ""
    duration_seconds: float = 0.0
    exit_code: int | None = None
    output_data: Any = None
    error_message: str | None = None
    observations: list[ObservationRecord] = field(default_factory=list)
    verification_result: VerificationResult | None = None
    evidence_refs: list[str] = field(default_factory=list)
    idempotency_key: str = ""
    sandbox_tier_used: str = "TIER_0_APP"

    def to_dict(self) -> dict[str, Any]:
        """Serialize ExecutionResult to a canonical dictionary."""
        d = asdict(self)
        d["status"] = self.status.value
        d["observations"] = [o.to_dict() for o in self.observations]
        d["verification_result"] = (
            self.verification_result.to_dict() if self.verification_result else None
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionResult:
        """Deserialize ExecutionResult from dictionary."""
        status = ExecutionStatus(data["status"])
        raw_obs = data.get("observations", [])
        observations: list[ObservationRecord] = [
            ObservationRecord.from_dict(o) if isinstance(o, dict) else o
            for o in raw_obs
        ]

        raw_ver = data.get("verification_result")
        verification_result: VerificationResult | None = None
        if raw_ver:
            verification_result = (
                VerificationResult.from_dict(raw_ver)
                if isinstance(raw_ver, dict)
                else raw_ver
            )

        return cls(
            execution_id=data["execution_id"],
            command_id=data["command_id"],
            task_id=data["task_id"],
            plan_id=data["plan_id"],
            plan_revision=int(data.get("plan_revision", 1)),
            node_id=data["node_id"],
            attempt_id=int(data.get("attempt_id", 1)),
            status=status,
            failure_class=data.get("failure_class"),
            started_at_utc=data.get("started_at_utc", ""),
            completed_at_utc=data.get("completed_at_utc", ""),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            exit_code=data.get("exit_code"),
            output_data=data.get("output_data"),
            error_message=data.get("error_message"),
            observations=observations,
            verification_result=verification_result,
            evidence_refs=list(data.get("evidence_refs", [])),
            idempotency_key=data.get("idempotency_key", ""),
            sandbox_tier_used=data.get("sandbox_tier_used", "TIER_0_APP"),
        )

    @classmethod
    def create_terminal(
        cls,
        command_id: str,
        task_id: str,
        plan_id: str,
        plan_revision: int,
        node_id: str,
        attempt_id: int,
        execution_id: str,
        status: ExecutionStatus,
        started_at_utc: str,
        exit_code: int | None = None,
        output_data: Any = None,
        error_message: str | None = None,
        failure_class: str | None = None,
        observations: list[ObservationRecord] | None = None,
        verification_result: VerificationResult | None = None,
        evidence_refs: list[str] | None = None,
        idempotency_key: str = "",
        sandbox_tier_used: str = "TIER_0_APP",
        completed_at_utc: str | None = None,
    ) -> ExecutionResult:
        """Create a terminal ExecutionResult, calculating completion timestamp and duration."""
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_str = completed_at_utc or now_dt.isoformat()

        duration = 0.0
        if started_at_utc:
            try:
                s_dt = datetime.datetime.fromisoformat(started_at_utc)
                c_dt = datetime.datetime.fromisoformat(now_str)
                duration = max(0.0, (c_dt - s_dt).total_seconds())
            except Exception:
                duration = 0.0

        return cls(
            execution_id=execution_id,
            command_id=command_id,
            task_id=task_id,
            plan_id=plan_id,
            plan_revision=plan_revision,
            node_id=node_id,
            attempt_id=attempt_id,
            status=status,
            failure_class=failure_class,
            started_at_utc=started_at_utc,
            completed_at_utc=now_str,
            duration_seconds=duration,
            exit_code=exit_code,
            output_data=output_data,
            error_message=error_message,
            observations=observations or [],
            verification_result=verification_result,
            evidence_refs=evidence_refs or [],
            idempotency_key=idempotency_key,
            sandbox_tier_used=sandbox_tier_used,
        )


__all__ = ["ExecutionResult", "ExecutionStatus"]
