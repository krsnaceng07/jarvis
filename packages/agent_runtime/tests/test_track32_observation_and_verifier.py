"""Unit tests for ObservationCollector, StateVerifier, freshness guards, and state drift detection."""

from __future__ import annotations

import datetime
from pathlib import Path
import tempfile

from jarvis_agent.execution.adapters.base import AdapterExecutionOutput
from jarvis_agent.execution.observation.collector import ObservationCollector
from jarvis_agent.execution.verification.verifier import StateVerifier
from jarvis_agent.orchestration.models.command import ExecutionCommand
from jarvis_agent.orchestration.models.observation import (
    ObservationRecord,
    ObservationRequirement,
)
from jarvis_agent.orchestration.models.risk import RiskAssessment, RiskClass
from jarvis_agent.orchestration.models.verification import (
    VerificationAssertion,
    VerificationRequirement,
)

DUMMY_RISK = RiskAssessment(
    risk_class=RiskClass.LOW,
    blast_radius="LOCAL",
    reversibility="REVERSIBLE",
    data_sensitivity="PUBLIC",
    external_effect="NONE",
    requires_operator_approval=False,
)


def test_observation_collector_and_cryptographic_evidence() -> None:
    collector = ObservationCollector()
    cmd = ExecutionCommand.create(
        command_id="cmd_obs_1",
        task_id="t1",
        plan_id="p1",
        node_id="n1",
        execution_id="e1",
        attempt_id=1,
        plan_revision=1,
        capability_target="browser.media_control",
        arguments={"action": "pause"},
        deadline_utc="2030-01-01T00:00:00Z",
        risk_assessment=DUMMY_RISK,
    )

    out = AdapterExecutionOutput(
        success=True,
        output_data={"action": "pause", "paused": True},
        raw_evidence={"media_state": {"paused": True, "currentTime": 50.0}},
    )

    req = ObservationRequirement(
        requirement_id="req_media_1",
        predicate_type="MEDIA_PAUSED",
        target="media_player",
    )

    records = collector.collect(cmd, out, requirements=[req])
    assert len(records) == 1
    rec = records[0]
    assert rec.success is True
    assert rec.evidence_ref is not None
    assert rec.evidence_ref.startswith("obs:req_media_1:")
    assert rec.raw_data["paused"] is True


def test_state_verifier_predicates_and_freshness() -> None:
    verifier = StateVerifier()

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    obs = ObservationRecord(
        observation_id="obs_1",
        node_id="n1",
        captured_at_utc=now_iso,
        success=True,
        raw_data={"paused": True, "exit_code": 0, "status": "ok"},
        evidence_ref="ev:n1:abc123",
    )

    # 1. Matching assertions
    req = VerificationRequirement(
        verification_id="ver_req_1",
        node_id="n1",
        assertions=[
            VerificationAssertion(
                assertion_id="a1",
                field_name="paused",
                assertion_type="MEDIA_PAUSED",
                expected_value=True,
            ),
            VerificationAssertion(
                assertion_id="a2",
                field_name="exit_code",
                assertion_type="EXIT_CODE_ZERO",
                expected_value=0,
            ),
            VerificationAssertion(
                assertion_id="a3",
                field_name="status",
                assertion_type="EQUALS",
                expected_value="ok",
            ),
        ],
    )

    res = verifier.verify("n1", [req], [obs])
    assert res.passed is True
    assert res.assertions_evaluated == 3
    assert res.assertions_passed == 3
    assert res.error_message is None

    # 2. Failing assertion
    req_fail = VerificationRequirement(
        verification_id="ver_req_2",
        node_id="n1",
        assertions=[
            VerificationAssertion(
                assertion_id="afail",
                field_name="status",
                assertion_type="EQUALS",
                expected_value="unexpected_val",
            )
        ],
    )
    res_fail = verifier.verify("n1", [req_fail], [obs])
    assert res_fail.passed is False
    assert res_fail.assertions_passed == 0
    assert "afail" in res_fail.diffs

    # 3. Freshness Guard Rejection
    old_time = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
    ).isoformat()
    stale_obs = ObservationRecord(
        observation_id="obs_stale",
        node_id="n1",
        captured_at_utc=old_time,
        success=True,
        raw_data={"paused": True},
        evidence_ref="ev:n1:stale",
    )
    res_stale = verifier.verify("n1", [req], [stale_obs], max_observation_age_seconds=60.0)
    assert res_stale.passed is False
    assert "Stale observation rejected" in str(res_stale.error_message)


def test_state_drift_detection() -> None:
    verifier = StateVerifier()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    obs = ObservationRecord(
        observation_id="obs_1",
        node_id="n1",
        captured_at_utc=now_iso,
        success=True,
        raw_data={"status": "ok"},
        evidence_ref="ev:n1:123",
    )

    # Baseline fingerprint drifted from current precondition state
    res_drift = verifier.verify(
        node_id="n1",
        requirements=None,
        observations=[obs],
        baseline_fingerprint="fp_hash_original_state",
        current_fingerprint="fp_hash_mutated_external_state",
    )
    assert res_drift.passed is False
    assert "Precondition state drift detected" in str(res_drift.error_message)
    assert "state_drift" in res_drift.diffs
