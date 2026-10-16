"""Phase 8 Operational Acceptance Suite 3: Runtime Health & Classified Rollback.

Scenarios:
- P8-015: External network outage classified as external_service and does NOT trigger model rollback (INV-HEALTH-001)
- P8-016: Tool implementation exception classified as tool_implementation and does NOT rollback model
- P8-017: Failure classified as unknown_inconclusive pauses rollback and requests operator inspection (INV-HEALTH-003)
- P8-018: Single verified critical safety failure triggers immediate automated rollback to known-good model
- P8-019: Rollback hysteresis prevents rapid promote/rollback flapping within cooldown period (INV-HEALTH-002)
- P8-020: Baseline-relative regression detector triggers alert when candidate latency degrades by >50% (INV-EVAL-002)
"""

import time

from jarvis_learning.evaluation.attribution import (
    FailureAttributionEngine,
    FailureAttributionEvidence,
    FailureCause,
    RollbackHysteresisController,
)
from jarvis_learning.evaluation.benchmark import BenchmarkResult
from jarvis_learning.evaluation.domain_benchmarks import (
    BaselineRelativeRegressionDetector,
    CanonicalEvaluationReport,
)
from jarvis_learning.evaluation.invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    OperationalTestEvidence,
    TestExecutionClassification,
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


def test_p8_015_external_network_outage_does_not_rollback():
    """P8-015: External network outage classified as external_service and does NOT trigger model rollback."""
    engine = FailureAttributionEngine()
    controller = RollbackHysteresisController()

    evidence = engine.attribute(
        error_message="HTTPConnectionPool(host='api.weather.local', port=80): Connection reset by peer: timeout",
        tool_name="get_weather",
    )

    assert evidence.primary_cause == FailureCause.EXTERNAL_SERVICE

    decision = controller.record_execution_outcome(
        evidence=evidence,
        is_critical_safety=False,
        last_known_good_model_id="model_v001_kg",
    )

    # Rollback must NOT trigger for external outages
    assert decision.rollback_triggered is False
    assert decision.paused_for_operator_inspection is False

    _record_evidence(
        "P8-015",
        "INV-HEALTH-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"cause": evidence.primary_cause.value, "rollback_triggered": decision.rollback_triggered},
    )


def test_p8_016_tool_implementation_bug_does_not_rollback():
    """P8-016: Tool implementation exception classified as tool_implementation and does NOT rollback model."""
    engine = FailureAttributionEngine()
    controller = RollbackHysteresisController()

    evidence = engine.attribute(
        error_message="TypeError: unsupported operand type(s) for +: 'int' and 'str'",
        traceback_str="File 'tools/calc.py', line 42, in compute: return a + b",
        tool_name="calc.compute",
    )

    assert evidence.primary_cause == FailureCause.TOOL_IMPLEMENTATION

    decision = controller.record_execution_outcome(
        evidence=evidence,
        is_critical_safety=False,
        last_known_good_model_id="model_v001_kg",
    )

    assert decision.rollback_triggered is False

    _record_evidence(
        "P8-016",
        "INV-HEALTH-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"cause": evidence.primary_cause.value, "rollback_triggered": decision.rollback_triggered},
    )


def test_p8_017_unknown_inconclusive_pauses_rollback_and_requests_inspection():
    """P8-017: Failure classified as unknown_inconclusive pauses rollback and requests operator inspection."""
    engine = FailureAttributionEngine()
    controller = RollbackHysteresisController()

    # Ambiguous error message with no clear blame
    evidence = engine.attribute(
        error_message="Task execution halted unexpectedly without specific error code",
        tool_name="custom_task",
    )

    assert evidence.primary_cause == FailureCause.UNKNOWN_INCONCLUSIVE

    decision = controller.record_execution_outcome(
        evidence=evidence,
        is_critical_safety=False,
        last_known_good_model_id="model_v001_kg",
    )

    # Must pause automatic rollback and request operator review
    assert decision.rollback_triggered is False
    assert decision.paused_for_operator_inspection is True
    assert "pending operator diagnostic inspection" in decision.alert_message

    _record_evidence(
        "P8-017",
        "INV-HEALTH-003",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"paused_for_inspection": decision.paused_for_operator_inspection},
    )


def test_p8_018_critical_safety_failure_triggers_immediate_rollback():
    """P8-018: Single verified critical safety failure triggers immediate automated rollback to known-good model."""
    engine = FailureAttributionEngine()
    controller = RollbackHysteresisController()

    evidence = engine.attribute(
        error_message="Model generated false completion claim without executing required verifier tool",
        tool_name="verifier.check",
    )

    assert evidence.primary_cause == FailureCause.MODEL_CAUSED

    decision = controller.record_execution_outcome(
        evidence=evidence,
        is_critical_safety=True,  # Critical safety failure
        last_known_good_model_id="model_v001_known_good",
        known_good_is_valid=True,
    )

    assert decision.rollback_triggered is True
    assert decision.target_model_id == "model_v001_known_good"
    assert decision.is_safe_degraded_mode is False

    _record_evidence(
        "P8-018",
        "INV-HEALTH-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"rollback_triggered": decision.rollback_triggered, "target": decision.target_model_id},
    )


def test_p8_019_rollback_hysteresis_and_flapping_cooldown():
    """P8-019: Rollback hysteresis prevents rapid promote/rollback flapping within cooldown period."""
    controller = RollbackHysteresisController(cooldown_window_seconds=3600.0)  # 1-hour cooldown
    now = time.time()

    evidence = FailureAttributionEvidence(
        primary_cause=FailureCause.MODEL_CAUSED,
        confidence=1.0,
        evidence_signals=("consecutive_failure",),
    )

    # First rollback triggers successfully
    d1 = controller.record_execution_outcome(
        evidence=evidence,
        is_critical_safety=True,
        timestamp=now,
        last_known_good_model_id="model_v001_kg",
    )
    assert d1.rollback_triggered is True

    # Immediate second rollback attempt within 10 minutes (600s < 3600s cooldown)
    d2 = controller.record_execution_outcome(
        evidence=evidence,
        is_critical_safety=True,
        timestamp=now + 600.0,
        last_known_good_model_id="model_v001_kg",
    )

    # Should be blocked by hysteresis to prevent flapping loop
    assert d2.rollback_triggered is False
    assert d2.paused_for_operator_inspection is True
    assert "anti-flapping hysteresis" in d2.alert_message

    _record_evidence(
        "P8-019",
        "INV-HEALTH-002",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"hysteresis_blocked": True},
    )


def test_p8_020_baseline_relative_latency_regression_alert():
    """P8-020: Baseline-relative regression detector triggers alert when candidate latency degrades by >50%."""
    results = [
        BenchmarkResult("case_01", "medium", True, "tool_a", "tool_a", False, "passed"),
        BenchmarkResult("case_02", "medium", True, "tool_b", "tool_b", False, "passed"),
    ]

    base_report = CanonicalEvaluationReport.create(
        report_id="eval_base",
        model_id="model_base",
        timestamp_iso="2026-09-17T23:00:00Z",
        environment_fingerprint="fp_win32",
        results=results,
    )
    cand_report = CanonicalEvaluationReport.create(
        report_id="eval_cand",
        model_id="model_cand",
        timestamp_iso="2026-09-17T23:30:00Z",
        environment_fingerprint="fp_win32",
        results=results,
    )

    detector = BaselineRelativeRegressionDetector(max_latency_degradation_pct=50.0)

    # Baseline latency: 100ms; Candidate latency: 180ms (+80% degradation > 50% limit)
    res = detector.compare(
        candidate_report=cand_report,
        baseline_report=base_report,
        candidate_avg_latency_ms=180.0,
        baseline_avg_latency_ms=100.0,
    )

    assert res.has_regression is True
    assert res.latency_alert is True
    assert res.latency_degradation_pct == 80.0
    assert any("LATENCY REGRESSION" in r for r in res.rejection_reasons)

    _record_evidence(
        "P8-020",
        "INV-EVAL-002",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"latency_degradation_pct": res.latency_degradation_pct},
    )
