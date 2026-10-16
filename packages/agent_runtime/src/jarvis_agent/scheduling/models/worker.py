"""WorkerIdentity and lifecycle tracking models for multi-process safety."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
from enum import Enum
from typing import Any


class WorkerStatus(str, Enum):
    """Lifecycle status of a scheduler worker process."""

    STARTED = "STARTED"
    ACTIVE = "ACTIVE"
    SUSPECTED_LOST = "SUSPECTED_LOST"
    FENCED = "FENCED"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class WorkerIdentity:
    """Identity and heartbeat record for a scheduler worker instance."""

    worker_id: str
    worker_epoch: int
    process_id: int
    host_identity: str
    started_at_utc: str
    last_heartbeat_utc: str
    status: WorkerStatus
    heartbeat_timeout_seconds: float = 15.0

    def is_heartbeat_stale(self, current_time_utc: str | None = None) -> bool:
        now_dt = (
            datetime.datetime.fromisoformat(current_time_utc)
            if current_time_utc
            else datetime.datetime.now(datetime.timezone.utc)
        )
        hb_dt = datetime.datetime.fromisoformat(self.last_heartbeat_utc)
        return (now_dt - hb_dt).total_seconds() > self.heartbeat_timeout_seconds

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkerIdentity:
        st = data["status"]
        if isinstance(st, str):
            st = WorkerStatus(st)
        return cls(
            worker_id=data["worker_id"],
            worker_epoch=int(data["worker_epoch"]),
            process_id=int(data["process_id"]),
            host_identity=data["host_identity"],
            started_at_utc=data["started_at_utc"],
            last_heartbeat_utc=data["last_heartbeat_utc"],
            status=st,
            heartbeat_timeout_seconds=float(data.get("heartbeat_timeout_seconds", 15.0)),
        )


__all__ = ["WorkerIdentity", "WorkerStatus"]
