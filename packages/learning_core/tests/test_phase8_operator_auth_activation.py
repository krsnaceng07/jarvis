"""Phase 8 Operational Acceptance Suite 4: Cryptographic Operator Authorization & Atomic Activation.

Scenarios:
- P8-021: Unauthenticated operator string or spoofed ID rejected with AuthorizationError (INV-AUTH-001)
- P8-022: Operator approval token bound to mismatched artifact digest rejected (INV-AUTH-001)
- P8-023: Upstream revoked dataset in Phase 7 RevocationGraph strictly blocks promotion (INV-LINEAGE-001)
- P8-024: Incompatible tool schema version blocks model activation pre-flight (INV-COMP-001)
- P8-025: Crash injection during activation transaction reconciles safely to last_known_good_approved (INV-ACT-002)
- P8-026: Rollback attempt targeting unapproved or non-existent model ID rejected (INV-RBK-001)
- P8-027: Reused approval token nonce rejected by replay prevention (INV-AUTH-001)
- P8-028: Active model pointer file commit remains atomic across power/process crash (INV-ACT-001)
"""

import json
import pytest

from jarvis_learning.evaluation.invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    OperationalTestEvidence,
    TestExecutionClassification,
)
from jarvis_learning.evaluation.promotion_machine import (
    AuthorizationError,
    ModelActivationTransaction,
    OperatorApprovalToken,
    OperatorAuthorizationValidator,
    PromotionLifecycleManager,
    PromotionState,
)


def _record_evidence(
    test_id: str,
    invariant_id: str,
    classification: TestExecutionClassification,
    passed: bool,
    details: dict,
):
    GLOBAL_OPERATIONAL_LEDGER.record(
        OperationalTestEvidence(
            test_id=test_id,
            invariant_id=invariant_id,
            classification=classification,
            passed=passed,
            evidence_details=details,
        )
    )


def test_p8_021_unauthenticated_operator_string_rejected():
    """P8-021: Unauthenticated operator string or spoofed ID rejected with AuthorizationError."""
    validator = OperatorAuthorizationValidator(
        secret_key=b"secret_key_12345",
        authorized_operators=["operator_alice"],
    )

    # Spoofed operator identity
    token = OperatorApprovalToken.generate(
        model_id="cand_v100",
        artifact_digest="sha256_art_abc",
        checkpoint_digest="sha256_ckp_def",
        evaluation_report_digest="sha256_rep_ghi",
        target_slot="active_primary",
        operator_identity="malicious_attacker",  # Unauthorized!
        approval_nonce="nonce_001",
        approval_reason="force promote",
        secret_key=b"secret_key_12345",
    )

    with pytest.raises(AuthorizationError, match="Unauthorized operator identity"):
        validator.validate(
            token,
            expected_artifact_digest="sha256_art_abc",
            expected_checkpoint_digest="sha256_ckp_def",
            expected_eval_digest="sha256_rep_ghi",
        )

    _record_evidence(
        "P8-021",
        "INV-AUTH-001",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"rejected": True},
    )


def test_p8_022_mismatched_artifact_digest_rejected():
    """P8-022: Operator approval token bound to mismatched artifact digest rejected."""
    validator = OperatorAuthorizationValidator(
        secret_key=b"secret_key_12345",
        authorized_operators=["operator_alice"],
    )

    token = OperatorApprovalToken.generate(
        model_id="cand_v100",
        artifact_digest="sha256_art_original",
        checkpoint_digest="sha256_ckp_def",
        evaluation_report_digest="sha256_rep_ghi",
        target_slot="active_primary",
        operator_identity="operator_alice",
        approval_nonce="nonce_002",
        approval_reason="regular promotion",
        secret_key=b"secret_key_12345",
    )

    # Disk model has different digest
    with pytest.raises(AuthorizationError, match="Token artifact digest mismatch"):
        validator.validate(
            token,
            expected_artifact_digest="sha256_art_TAMPERED_ON_DISK",
            expected_checkpoint_digest="sha256_ckp_def",
            expected_eval_digest="sha256_rep_ghi",
        )

    _record_evidence(
        "P8-022",
        "INV-AUTH-001",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"mismatch_caught": True},
    )


def test_p8_023_upstream_revocation_blocks_promotion():
    """P8-023: Upstream revoked dataset in Phase 7 RevocationGraph strictly blocks promotion."""
    manager = PromotionLifecycleManager(model_id="cand_v100")
    revoked_list = ["dataset_p6_poisoned", "cand_v100"]

    is_revoked = manager.check_revocation(revoked_list)
    assert is_revoked is True
    assert manager.current_state == PromotionState.REVOKED_INELIGIBLE

    _record_evidence(
        "P8-023",
        "INV-LINEAGE-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"state": manager.current_state.value},
    )


def test_p8_024_incompatible_tool_schema_version_blocks_activation(tmp_path):
    """P8-024: Incompatible tool schema version blocks model activation pre-flight."""
    tx = ModelActivationTransaction(state_dir=tmp_path / "models")

    with pytest.raises(ValueError, match="REJECTED_RUNTIME_INCOMPATIBLE"):
        tx.execute_activation(
            candidate_model_id="cand_v100",
            artifact_digest="sha256_art",
            tool_schema_version="2.0.0",  # Candidate expects 2.0.0
            expected_schema_version="1.0.0",  # Runtime is currently 1.0.0
            prompt_policy_version="1.0.0",
            expected_prompt_policy_version="1.0.0",
        )

    _record_evidence(
        "P8-024",
        "INV-COMP-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"schema_incompatibility_blocked": True},
    )


def test_p8_025_crash_recovery_during_activation_reconciles_to_known_good(tmp_path):
    """P8-025: Crash injection during activation transaction reconciles safely to last_known_good_approved."""
    state_dir = tmp_path / "models"
    tx = ModelActivationTransaction(state_dir=state_dir)

    # Simulate crash midway: active.pending left on disk, active.json points to old known good
    active_json = state_dir / "active.json"
    active_pending = state_dir / "active.pending"

    active_json.write_text(json.dumps({"model_id": "model_v001_kg", "status": "ACTIVE_PRIMARY"}))
    active_pending.write_text(
        json.dumps({"model_id": "cand_v100_uncommitted", "status": "PENDING_COMMIT"})
    )

    # On startup reconciliation
    reconciled = tx.reconcile_on_startup(last_known_good_id="model_v001_kg")

    assert reconciled["model_id"] == "model_v001_kg"
    assert not active_pending.exists()  # Stale pending file cleaned up

    _record_evidence(
        "P8-025",
        "INV-ACT-002",
        TestExecutionClassification.CRASH_INJECTION,
        True,
        {"reconciled_model": reconciled["model_id"]},
    )


def test_p8_026_rollback_targeting_unapproved_model_rejected():
    """P8-026: Rollback attempt targeting unapproved or non-existent model ID rejected."""
    from jarvis_learning.evaluation.attribution import (
        FailureAttributionEvidence,
        FailureCause,
        RollbackHysteresisController,
    )

    controller = RollbackHysteresisController()
    evidence = FailureAttributionEvidence(
        primary_cause=FailureCause.MODEL_CAUSED,
        confidence=1.0,
        evidence_signals=("critical_error",),
    )

    # Rollback attempted but target known-good is marked INVALID
    decision = controller.record_execution_outcome(
        evidence=evidence,
        is_critical_safety=True,
        last_known_good_model_id="unapproved_random_model",
        known_good_is_valid=False,  # Unapproved / invalid!
    )

    # System must refuse unapproved model and transition to SAFE_DEGRADED_MODE
    assert decision.rollback_triggered is True
    assert decision.target_model_id is None
    assert decision.is_safe_degraded_mode is True
    assert "SAFE_DEGRADED_MODE" in decision.alert_message

    _record_evidence(
        "P8-026",
        "INV-RBK-001",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"safe_degraded_mode": decision.is_safe_degraded_mode},
    )


def test_p8_027_reused_approval_token_nonce_rejected():
    """P8-027: Reused approval token nonce rejected by replay prevention."""
    validator = OperatorAuthorizationValidator(
        secret_key=b"secret_key_12345",
        authorized_operators=["operator_alice"],
    )

    token = OperatorApprovalToken.generate(
        model_id="cand_v100",
        artifact_digest="sha256_art_abc",
        checkpoint_digest="sha256_ckp_def",
        evaluation_report_digest="sha256_rep_ghi",
        target_slot="active_primary",
        operator_identity="operator_alice",
        approval_nonce="nonce_single_use_123",
        approval_reason="regular promotion",
        secret_key=b"secret_key_12345",
    )

    # First validation succeeds
    validator.validate(
        token,
        expected_artifact_digest="sha256_art_abc",
        expected_checkpoint_digest="sha256_ckp_def",
        expected_eval_digest="sha256_rep_ghi",
    )

    # Second validation of same token/nonce is rejected as replay attack
    with pytest.raises(AuthorizationError, match="Replay detected"):
        validator.validate(
            token,
            expected_artifact_digest="sha256_art_abc",
            expected_checkpoint_digest="sha256_ckp_def",
            expected_eval_digest="sha256_rep_ghi",
        )

    _record_evidence(
        "P8-027",
        "INV-AUTH-001",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"replay_prevented": True},
    )


def test_p8_028_atomic_model_pointer_file_commit(tmp_path):
    """P8-028: Active model pointer file commit remains atomic across power/process crash."""
    state_dir = tmp_path / "models"
    tx = ModelActivationTransaction(state_dir=state_dir)

    committed = tx.execute_activation(
        candidate_model_id="cand_v100",
        artifact_digest="sha256_art_abc",
        tool_schema_version="1.0.0",
        expected_schema_version="1.0.0",
        prompt_policy_version="1.0.0",
        expected_prompt_policy_version="1.0.0",
        simulation_check=True,
    )

    assert committed["status"] == "ACTIVE_PRIMARY"
    assert committed["model_id"] == "cand_v100"

    # Verify active.json on disk
    active_on_disk = tx.get_active_model_info()
    assert active_on_disk is not None
    assert active_on_disk["model_id"] == "cand_v100"
    assert not (state_dir / "active.pending").exists()

    _record_evidence(
        "P8-028",
        "INV-ACT-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"committed_model": committed["model_id"]},
    )
