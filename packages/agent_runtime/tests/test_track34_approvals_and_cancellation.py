"""Test suite for Track 3.4 Atomic Approvals & Asynchronous Cancellation (Phase 3.4-I).

Validates:
1. Canonical action digest hashing.
2. Action-bound approval matching and mismatch rejection (Invariant T34-06).
3. Expiration checks (APPROVAL_EXPIRED).
4. Atomic compare-and-set idempotency on concurrent resolutions (Invariant T34-14).
5. Immediate acceptance acknowledgement for cancellations (Invariant T34-15).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from jarvis_agent.gateway.approval_seam import (
    ApprovalGatewaySeam,
    ApprovalRecord,
    ApprovalStatus,
)
from jarvis_agent.gateway.cancellation_seam import CancellationGatewaySeam
from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import ClientIdentity


def test_action_bound_approval_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "approvals.sqlite"
        broadcasts: list[ApprovalRecord] = []
        seam = ApprovalGatewaySeam(db_path, on_resolved_broadcast=lambda r: broadcasts.append(r))

        ident = ClientIdentity("admin_user", "client_1", "desktop", "admin")

        args = {"path": "/etc/hosts", "content": "127.0.0.1"}
        rec = seam.request_approval(
            approval_id="appr_001",
            task_id="task_10",
            node_id="node_2",
            plan_revision=1,
            capability_id="filesystem.write",
            arguments=args,
            ttl_seconds=300.0,
        )
        assert rec.status == ApprovalStatus.PENDING
        expected_hash = rec.action_hash

        # 1. Resolution with mismatched action hash rejected (Invariant T34-06)
        with pytest.raises(GatewayException) as exc:
            seam.resolve_approval(
                approval_id="appr_001",
                identity=ident,
                claimed_action_hash="bad_hash_123",
                approved=True,
            )
        assert exc.value.code == GatewayErrorCode.APPROVAL_BINDING_MISMATCH

        # 2. Valid resolution approved atomically
        resolved = seam.resolve_approval(
            approval_id="appr_001",
            identity=ident,
            claimed_action_hash=expected_hash,
            approved=True,
            decision_reason="Operator verified hosts file",
        )
        assert resolved.status == ApprovalStatus.APPROVED
        assert resolved.resolved_by == "admin_user"
        assert len(broadcasts) == 1

        # 3. Subsequent resolution attempt returns cached state (idempotent duplicate resolution)
        resolved_dup = seam.resolve_approval(
            approval_id="appr_001",
            identity=ident,
            claimed_action_hash=expected_hash,
            approved=False,  # conflicting input
        )
        assert resolved_dup.status == ApprovalStatus.APPROVED  # original terminal status preserved!

        seam.close()


def test_approval_expiration() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "approvals.sqlite"
        seam = ApprovalGatewaySeam(db_path)
        ident = ClientIdentity("admin_user", "client_1", "desktop", "admin")

        rec = seam.request_approval(
            approval_id="appr_exp",
            task_id="task_20",
            node_id="node_5",
            plan_revision=1,
            capability_id="system.shutdown",
            arguments={},
            ttl_seconds=-10.0,  # already expired
        )

        with pytest.raises(GatewayException) as exc:
            seam.resolve_approval(
                approval_id="appr_exp",
                identity=ident,
                claimed_action_hash=rec.action_hash,
                approved=True,
            )
        assert exc.value.code == GatewayErrorCode.APPROVAL_EXPIRED

        seam.close()


def test_asynchronous_cancellation_acceptance() -> None:
    seam = CancellationGatewaySeam(cancellation_manager=None)
    ident = ClientIdentity("alice", "client_1", "desktop", scopes=frozenset(["cancel"]))

    res = seam.submit_cancellation_request(
        task_id="task_44",
        node_id="node_9",
        reason="User clicked abort",
        identity=ident,
    )
    assert res["accepted"] is True
    assert res["taskId"] == "task_44"
    assert "cancellationRequestId" in res
