"""Atomic action-bound approval transport seam for Track 3.4.

Enforces Invariant T34-06: Approval binds to exact canonical action digest.
Enforces Invariant T34-07: Zero scheduler state changes (approval is an orthogonal Track 3.1 condition).
Enforces Invariant T34-14: Atomic compare-and-set state transitions (first terminal resolution wins).
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import ClientIdentity


class ApprovalStatus(str, Enum):
    """Lifecycle states of an action-bound approval request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


def compute_canonical_action_hash(
    task_id: str,
    node_id: str,
    plan_revision: int,
    capability_id: str,
    arguments: dict[str, Any],
    side_effect_class: str = "NON_IDEMPOTENT_MUTATION",
    target_resource: str = "",
) -> str:
    """Compute deterministic SHA-256 digest over the exact action parameters."""
    canonical_args = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
    payload = f"{task_id}:{node_id}:{plan_revision}:{capability_id}:{canonical_args}:{side_effect_class}:{target_resource}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    """Authoritative record of an approval state."""

    approval_id: str
    action_hash: str
    task_id: str
    node_id: str
    plan_revision: int
    capability_id: str
    status: ApprovalStatus
    requested_by: str
    resolved_by: str | None
    created_at_utc: str
    expires_at_utc: str
    resolved_at_utc: str | None = None
    decision_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "action_hash": self.action_hash,
            "task_id": self.task_id,
            "node_id": self.node_id,
            "plan_revision": self.plan_revision,
            "capability_id": self.capability_id,
            "status": self.status.value,
            "requested_by": self.requested_by,
            "resolved_by": self.resolved_by,
            "created_at_utc": self.created_at_utc,
            "expires_at_utc": self.expires_at_utc,
            "resolved_at_utc": self.resolved_at_utc,
            "decision_reason": self.decision_reason,
        }


class ApprovalGatewaySeam:
    """Thread-safe SQLite WAL manager enforcing atomic action-bound approvals."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        on_resolved_broadcast: Callable[[ApprovalRecord], None] | None = None,
    ) -> None:
        self.db_path = str(db_path or ":memory:")
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.on_resolved_broadcast = on_resolved_broadcast
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gateway_approvals (
                    approval_id TEXT PRIMARY KEY,
                    action_hash TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    plan_revision INTEGER NOT NULL,
                    capability_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    resolved_by TEXT,
                    created_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    resolved_at_utc TEXT,
                    decision_reason TEXT
                );
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_gw_appr_task ON gateway_approvals(task_id, node_id);"
            )

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def request_approval(
        self,
        approval_id: str,
        task_id: str,
        node_id: str,
        plan_revision: int,
        capability_id: str,
        arguments: dict[str, Any],
        requested_by: str = "orchestrator",
        ttl_seconds: float = 300.0,
        side_effect_class: str = "NON_IDEMPOTENT_MUTATION",
        target_resource: str = "",
    ) -> ApprovalRecord:
        """Create and store a new PENDING action-bound approval."""
        action_hash = compute_canonical_action_hash(
            task_id=task_id,
            node_id=node_id,
            plan_revision=plan_revision,
            capability_id=capability_id,
            arguments=arguments,
            side_effect_class=side_effect_class,
            target_resource=target_resource,
        )
        now = datetime.datetime.now(datetime.timezone.utc)
        now_str = now.isoformat()
        exp_str = (now + datetime.timedelta(seconds=ttl_seconds)).isoformat()

        rec = ApprovalRecord(
            approval_id=approval_id,
            action_hash=action_hash,
            task_id=task_id,
            node_id=node_id,
            plan_revision=plan_revision,
            capability_id=capability_id,
            status=ApprovalStatus.PENDING,
            requested_by=requested_by,
            resolved_by=None,
            created_at_utc=now_str,
            expires_at_utc=exp_str,
        )

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO gateway_approvals (
                    approval_id, action_hash, task_id, node_id, plan_revision, capability_id,
                    status, requested_by, resolved_by, created_at_utc, expires_at_utc,
                    resolved_at_utc, decision_reason
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, NULL, ?, ?, NULL, '');
                """,
                (
                    approval_id,
                    action_hash,
                    task_id,
                    node_id,
                    plan_revision,
                    capability_id,
                    requested_by,
                    now_str,
                    exp_str,
                ),
            )
        return rec

    def resolve_approval(
        self,
        approval_id: str,
        identity: ClientIdentity,
        claimed_action_hash: str,
        approved: bool,
        decision_reason: str = "",
    ) -> ApprovalRecord:
        """Atomically resolve approval request.

        Enforces Invariant T34-06: Validates exact action_hash match.
        Enforces Invariant T34-14: Atomic compare-and-set on PENDING status.
        """
        if not identity.has_scope("approve") and identity.auth_tier != "admin":
            raise GatewayException(
                code=GatewayErrorCode.SESSION_FORBIDDEN,
                message=f"Principal '{identity.user_id}' lacks 'approve' scope.",
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        now_str = now.isoformat()

        with self._conn:
            cur = self._conn.execute(
                "SELECT * FROM gateway_approvals WHERE approval_id = ?;", (approval_id,)
            )
            row = cur.fetchone()
            if not row:
                raise GatewayException(
                    code=GatewayErrorCode.INVALID_PARAMS,
                    message=f"Approval ID '{approval_id}' not found.",
                )

            stored_hash = row["action_hash"]
            stored_status = ApprovalStatus(row["status"])
            exp = datetime.datetime.fromisoformat(row["expires_at_utc"])

            # 1. Action hash verification
            if stored_hash != claimed_action_hash:
                raise GatewayException(
                    code=GatewayErrorCode.APPROVAL_BINDING_MISMATCH,
                    message="Approval rejected: action digest mismatch.",
                    data={"expected": stored_hash, "received": claimed_action_hash},
                )

            # 2. Idempotent duplicate check: already terminal?
            if stored_status != ApprovalStatus.PENDING:
                # Return cached terminal resolution
                return self._row_to_record(row)

            # 3. Expiration check
            if now >= exp:
                self._conn.execute(
                    "UPDATE gateway_approvals SET status = 'EXPIRED' WHERE approval_id = ?;",
                    (approval_id,),
                )
                raise GatewayException(
                    code=GatewayErrorCode.APPROVAL_EXPIRED,
                    message=f"Approval '{approval_id}' has expired.",
                )

            # 4. Atomic compare-and-set
            target_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            self._conn.execute(
                """
                UPDATE gateway_approvals
                SET status = ?, resolved_by = ?, resolved_at_utc = ?, decision_reason = ?
                WHERE approval_id = ? AND status = 'PENDING';
                """,
                (target_status.value, identity.user_id, now_str, decision_reason, approval_id),
            )

            # Re-fetch updated row
            cur3 = self._conn.execute(
                "SELECT * FROM gateway_approvals WHERE approval_id = ?;", (approval_id,)
            )
            updated_row = cur3.fetchone()
            record = self._row_to_record(updated_row)

        if self.on_resolved_broadcast:
            self.on_resolved_broadcast(record)

        return record

    def _row_to_record(self, row: Any) -> ApprovalRecord:
        return ApprovalRecord(
            approval_id=row["approval_id"],
            action_hash=row["action_hash"],
            task_id=row["task_id"],
            node_id=row["node_id"],
            plan_revision=int(row["plan_revision"]),
            capability_id=row["capability_id"],
            status=ApprovalStatus(row["status"]),
            requested_by=row["requested_by"],
            resolved_by=row["resolved_by"],
            created_at_utc=row["created_at_utc"],
            expires_at_utc=row["expires_at_utc"],
            resolved_at_utc=row["resolved_at_utc"],
            decision_reason=row["decision_reason"] or "",
        )


__all__ = [
    "ApprovalStatus",
    "ApprovalRecord",
    "compute_canonical_action_hash",
    "ApprovalGatewaySeam",
]
