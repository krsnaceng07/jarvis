"""packages/learning_core/tests/test_phase9_operator_cli.py — Tests for Category 7 (P9-042 to P9-045).

Validates:
- P9-042: jarvis learn review displays candidate metrics, Wilson CI bounds, and bias warnings.
- P9-043: jarvis learn approve requires human confirmation of the 6-character digest suffix (INV-P9-AUTH-001).
- P9-044: Forged or expired HMAC approval tokens are rejected by the promotion engine.
- P9-045: jarvis learn verify-ledger validates the complete cryptographic chain.
"""

from __future__ import annotations

import hashlib
import json
import time
import pytest

from jarvis_learning.cli import (
    handle_approve_token,
    handle_review,
    handle_verify_ledger,
)
from jarvis_learning.evaluation.invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    OperationalTestEvidence,
    TestExecutionClassification,
)
from jarvis_learning.evaluation.promotion_machine import (
    AuthorizationError,
    OperatorApprovalToken,
    OperatorAuthorizationValidator,
)


def _record_evidence(
    test_id: str,
    invariant_id: str,
    classification: TestExecutionClassification,
    passed: bool,
    details: dict,
) -> None:
    GLOBAL_OPERATIONAL_LEDGER.record(
        OperationalTestEvidence(
            test_id=test_id,
            invariant_id=invariant_id,
            classification=classification,
            passed=passed,
            evidence_details=details,
        )
    )


def test_p9_042_cli_review_dashboard(capsys) -> None:
    """P9-042: jarvis learn review displays candidate metrics, Wilson CI bounds, and bias warnings."""
    res = handle_review("model_cand_01", as_json=True)
    assert res == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["candidate_id"] == "model_cand_01"
    assert data["qualified"] is True
    assert data["wilson_ci_lower"] >= 0.80
    assert "filesystem" in data["task_families"]

    _record_evidence(
        "P9-042",
        "INV-P9-AUTH-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"candidate_id": data["candidate_id"], "wilson_ci_lower": data["wilson_ci_lower"]},
    )


def test_p9_043_cli_approve_requires_human_digest_confirmation(capsys) -> None:
    """P9-043: jarvis learn approve requires human confirmation of the 6-character digest suffix (INV-P9-AUTH-001)."""
    dummy_bytes = b"MODEL_WEIGHTS_FOR_candidate_model_x"
    expected_hash = hashlib.sha256(dummy_bytes).hexdigest()
    valid_suffix = expected_hash[-6:].upper()

    # 1. Attempt approval with missing / incorrect suffix -> must fail
    fail_res = handle_approve_token(
        candidate_id="candidate_model_x",
        confirm_suffix="WRONG!",
        operator_id="admin",
        role="admin",
        as_json=True,
    )
    assert fail_res == 1
    err_out = json.loads(capsys.readouterr().out)
    assert err_out["status"] == "rejected"
    assert (
        "Automated bypass without human digest confirmation is strictly prohibited"
        in err_out["error"]
    )

    # 2. Attempt approval with valid matching suffix -> succeeds
    success_res = handle_approve_token(
        candidate_id="candidate_model_x",
        confirm_suffix=valid_suffix,
        operator_id="security_lead",
        role="admin",
        as_json=True,
    )
    assert success_res == 0
    ok_out = json.loads(capsys.readouterr().out)
    assert ok_out["status"] == "approved"
    assert ok_out["candidate_id"] == "candidate_model_x"
    assert ok_out["token_id"].startswith("optok_")
    assert len(ok_out["signature"]) > 10

    _record_evidence(
        "P9-043",
        "INV-P9-AUTH-001",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"human_confirmation_verified": True, "token_id": ok_out["token_id"]},
    )


def test_p9_044_forged_or_expired_approval_tokens_rejected() -> None:
    """P9-044: Forged or expired HMAC approval tokens are rejected by the promotion engine."""
    validator = OperatorAuthorizationValidator(
        secret_key=b"jarvis_operator_secret",
        authorized_operators=["operator_alice"],
    )

    # Expired token (issued 7200s ago, well past 3600s max age)
    expired_token = OperatorApprovalToken.generate(
        model_id="cand_v100",
        artifact_digest="sha256_art_abc",
        checkpoint_digest="sha256_ckp_def",
        evaluation_report_digest="sha256_rep_ghi",
        target_slot="active",
        operator_identity="operator_alice",
        approval_nonce="nonce_expired",
        approval_reason="routine",
        secret_key=b"jarvis_operator_secret",
        timestamp=time.time() - 7200.0,
    )

    with pytest.raises(AuthorizationError, match="expired"):
        validator.validate(
            expired_token,
            expected_artifact_digest="sha256_art_abc",
            expected_checkpoint_digest="sha256_ckp_def",
            expected_eval_digest="sha256_rep_ghi",
        )

    # Forged signature token
    forged_token = OperatorApprovalToken.generate(
        model_id="cand_v100",
        artifact_digest="sha256_art_abc",
        checkpoint_digest="sha256_ckp_def",
        evaluation_report_digest="sha256_rep_ghi",
        target_slot="active",
        operator_identity="operator_alice",
        approval_nonce="nonce_forged",
        approval_reason="routine",
        secret_key=b"wrong_secret_key_attacker",  # Forged!
    )

    with pytest.raises(AuthorizationError, match="Cryptographic signature mismatch"):
        validator.validate(
            forged_token,
            expected_artifact_digest="sha256_art_abc",
            expected_checkpoint_digest="sha256_ckp_def",
            expected_eval_digest="sha256_rep_ghi",
        )

    _record_evidence(
        "P9-044",
        "INV-P9-AUTH-001",
        TestExecutionClassification.SECURITY_BOUNDARY,
        True,
        {"expired_rejected": True, "forged_signature_rejected": True},
    )


def test_p9_045_cli_verify_ledger_validates_merkle_chain(capsys) -> None:
    """P9-045: jarvis learn verify-ledger validates the complete cryptographic chain."""
    res = handle_verify_ledger(as_json=True)
    assert res == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "valid"
    assert len(data["merkle_root"]) == 64
    assert data["total_entries"] > 0

    _record_evidence(
        "P9-045",
        "INV-P9-EVAL-003",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"ledger_status": data["status"], "merkle_root": data["merkle_root"]},
    )
