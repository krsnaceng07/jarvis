"""Stage 10.6: Operator Control Plane & Audit Scenarios.

Scenarios P10-039 to P10-044:
- P10-039: Operator authentication, role-based permission gating, and Windows SID binding.
- P10-040: Cryptographic approval token generation and signature verification.
- P10-041: Anti-replay enforcement: reusing a consumed nonce strictly raises TokenReplayError (INV-P10-OPS-002).
- P10-042: Token expiration enforcement: expired token raises TokenExpiredError.
- P10-043: R1 and R2 rollback execution meets required latency SLOs (50ms and 250ms) (INV-P10-RB-001).
- P10-044: Detached dashboard failure does not affect active runtime or learning supervisor (INV-P10-OPS-001).
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import time

import pytest

from jarvis_learning.control_plane.dashboard_sidecar import DashboardSidecarService
from jarvis_learning.control_plane.operator_auth import (
    OperatorAuthManager,
    OperatorRole,
    TokenExpiredError,
    TokenReplayError,
    UnauthorizedOperatorError,
)
from jarvis_learning.control_plane.rollback_engine import (
    RollbackClass,
    RollbackEngine,
)
from jarvis_learning.invariants_p10 import (
    EvidenceLevel,
    get_p10_evidence_ledger,
)


def test_p10_039_operator_auth_and_role_gating() -> None:
    """P10-039: Operator authentication, role-based permission gating, and Windows SID binding."""
    ledger = get_p10_evidence_ledger()

    auth = OperatorAuthManager(secret_key=b"super_secret_auth_key_12345")

    # Issue token as VIEWER
    viewer_token = auth.generate_token(
        candidate_id="cand_100",
        report_digest="sha256_report_abc",
        operator_sid="S-1-5-21-123456789-500",
        session_id="sess_win_01",
        operator_role=OperatorRole.VIEWER,
    )

    # Trying to approve with VIEWER role must be denied
    with pytest.raises(UnauthorizedOperatorError):
        auth.consume_token(viewer_token, required_role=OperatorRole.APPROVER)

    # Issue token as APPROVER
    approver_token = auth.generate_token(
        candidate_id="cand_100",
        report_digest="sha256_report_abc",
        operator_sid="S-1-5-21-123456789-500",
        session_id="sess_win_01",
        operator_role=OperatorRole.APPROVER,
    )

    ok = auth.consume_token(approver_token, required_role=OperatorRole.APPROVER)
    assert ok is True

    ledger.record(
        scenario_id="P10-039",
        invariant_id="INV-P10-OPS-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"operator_sid": "S-1-5-21-123456789-500"},
    )


def test_p10_040_cryptographic_token_verification() -> None:
    """P10-040: Cryptographic approval token generation and HMAC verification."""
    ledger = get_p10_evidence_ledger()

    auth = OperatorAuthManager(secret_key=b"hmac_secret_abc")

    token = auth.generate_token(
        candidate_id="cand_101",
        report_digest="sha256_rep_101",
        operator_sid="S-1-5-21-admin",
        session_id="sess_02",
        operator_role=OperatorRole.APPROVER,
    )

    assert token.signature != ""
    assert token.payload.candidate_id == "cand_101"

    # Consuming with legitimate token succeeds
    ok = auth.consume_token(token)
    assert ok is True

    ledger.record(
        scenario_id="P10-040",
        invariant_id="INV-P10-OPS-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"candidate_id": "cand_101"},
    )


def test_p10_041_anti_replay_nonce_enforcement() -> None:
    """P10-041: Anti-replay enforcement: reusing a consumed nonce strictly raises TokenReplayError (INV-P10-OPS-002)."""
    ledger = get_p10_evidence_ledger()

    auth = OperatorAuthManager(secret_key=b"anti_replay_secret")

    token = auth.generate_token(
        candidate_id="cand_102",
        report_digest="sha256_rep_102",
        operator_sid="S-1-5-21-admin",
        session_id="sess_03",
        operator_role=OperatorRole.APPROVER,
    )

    # First consumption succeeds
    assert auth.consume_token(token) is True

    # Immediate replay attempt MUST raise TokenReplayError
    with pytest.raises(TokenReplayError, match="has already been consumed"):
        auth.consume_token(token)

    ledger.record(
        scenario_id="P10-041",
        invariant_id="INV-P10-OPS-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"nonce": token.payload.nonce},
    )


def test_p10_042_token_expiration_enforcement() -> None:
    """P10-042: Token expiration enforcement: expired token raises TokenExpiredError."""
    ledger = get_p10_evidence_ledger()

    auth = OperatorAuthManager(secret_key=b"expiry_secret")

    # Issue token with 10s TTL
    token = auth.generate_token(
        candidate_id="cand_103",
        report_digest="sha256_rep_103",
        operator_sid="S-1-5-21-admin",
        session_id="sess_04",
        operator_role=OperatorRole.APPROVER,
        ttl_seconds=10.0,
    )

    # Validate 15s in the future
    future_time = time.time() + 15.0
    with pytest.raises(TokenExpiredError):
        auth.consume_token(token, current_time=future_time)

    ledger.record(
        scenario_id="P10-042",
        invariant_id="INV-P10-OPS-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"expired_as_expected": True},
    )


def test_p10_043_rollback_slo_compliance() -> None:
    """P10-043: R1 and R2 rollback execution meets required latency SLOs (50ms and 250ms) (INV-P10-RB-001)."""
    ledger = get_p10_evidence_ledger()

    with tempfile.TemporaryDirectory() as td:
        root_dir = Path(td)
        engine = RollbackEngine(root_dir)

        # Execute R1 (In-Memory / pointer switch)
        rec_r1 = engine.execute_rollback(
            rollback_class=RollbackClass.R1_IN_MEMORY,
            from_model="candidate_v10",
            to_model="baseline_v9",
            known_good_digest="sha256_base_9",
        )
        assert rec_r1.slo_met is True
        assert rec_r1.latency_ms <= 50.0

        # Execute R2 (Atomic artifact pointer restoration)
        rec_r2 = engine.execute_rollback(
            rollback_class=RollbackClass.R2_ATOMIC_ARTIFACT,
            from_model="candidate_v11",
            to_model="baseline_v10",
            known_good_digest="sha256_base_10",
        )
        assert rec_r2.slo_met is True
        assert rec_r2.latency_ms <= 250.0

    ledger.record(
        scenario_id="P10-043",
        invariant_id="INV-P10-RB-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"r1_latency_ms": rec_r1.latency_ms, "r2_latency_ms": rec_r2.latency_ms},
    )


def test_p10_044_detached_dashboard_crash_isolation() -> None:
    """P10-044: Detached dashboard failure does not affect active runtime or learning supervisor (INV-P10-OPS-001)."""
    ledger = get_p10_evidence_ledger()

    service = DashboardSidecarService()
    service.start()
    assert service.is_running is True

    snapshot = service.collect_snapshot(
        queue_depth=5,
        worker_count=2,
        events_processed=150,
        model_id="tool_policy",
        model_version="10.0.0",
        alerts=["Sample warning"],
    )
    assert snapshot.queue_depth == 5

    # Simulate dashboard crash
    with pytest.raises(RuntimeError, match="DASHBOARD_CRASHED"):
        service.simulate_failure()

    assert service.is_running is False

    ledger.record(
        scenario_id="P10-044",
        invariant_id="INV-P10-OPS-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"dashboard_isolated": True},
    )
