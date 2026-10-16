"""Two-phase asynchronous cancellation models and confirmation records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
from enum import Enum
from typing import Any


class CancellationConfirmationStatus(str, Enum):
    """Confirmation status of an execution abort request."""

    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED_TERMINATED = "CONFIRMED_TERMINATED"
    FAILED_TO_TERMINATE = "FAILED_TO_TERMINATE"
    UNCONFIRMED_EXTERNAL = "UNCONFIRMED_EXTERNAL"


@dataclass(frozen=True, slots=True)
class CancellationRequest:
    """Authoritative intent to cancel a task, plan, or node."""

    target_id: str  # task_id, plan_id, or node_id
    target_type: str  # "TASK", "PLAN", or "NODE"
    requested_by: str  # operator, timeout, or parent task
    reason: str
    requested_at_utc: str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CancellationRecord:
    """Outcome of attempting to cancel an ongoing execution in Track 3.2."""

    execution_id: str
    node_id: str
    status: CancellationConfirmationStatus
    confirmed_at_utc: str
    details: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


__all__ = [
    "CancellationConfirmationStatus",
    "CancellationRecord",
    "CancellationRequest",
]
