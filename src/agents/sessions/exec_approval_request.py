"""Exec approval request store and manager — mirrors OpenClaw exec approval pipeline."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Literal

ApprovalStatus = Literal["pending", "approved", "denied", "timeout"]


@dataclass
class ExecApprovalRecord:
    approval_id: str
    command: str
    cwd: str
    session_id: str
    status: ApprovalStatus = "pending"
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            self.created_at = time.time()


class ExecApprovalStore:
    """In-memory + SQLite store for pending command approvals."""

    def __init__(self) -> None:
        self._store: dict[str, ExecApprovalRecord] = {}

    def create_request(self, command: str, cwd: str, session_id: str) -> ExecApprovalRecord:
        approval_id = str(uuid.uuid4())
        rec = ExecApprovalRecord(
            approval_id=approval_id,
            command=command,
            cwd=cwd,
            session_id=session_id,
        )
        self._store[approval_id] = rec
        return rec

    def get(self, approval_id: str) -> ExecApprovalRecord | None:
        return self._store.get(approval_id)

    def respond(self, approval_id: str, approved: bool) -> ExecApprovalRecord | None:
        rec = self._store.get(approval_id)
        if not rec:
            return None
        rec.status = "approved" if approved else "denied"
        return rec

    def poll_status(self, approval_id: str, timeout_s: float = 30.0) -> ApprovalStatus:
        rec = self._store.get(approval_id)
        if not rec:
            return "denied"
        if rec.status != "pending":
            return rec.status
        if time.time() - rec.created_at > timeout_s:
            rec.status = "timeout"
            return "timeout"
        return "pending"


# Global singleton store instance
GLOBAL_EXEC_APPROVAL_STORE = ExecApprovalStore()

__all__ = [
    "ApprovalStatus",
    "ExecApprovalRecord",
    "ExecApprovalStore",
    "GLOBAL_EXEC_APPROVAL_STORE",
]
