"""Phase 8 Operational Acceptance Suite 1: Benchmark & Regression Gating.

Scenarios:
- P8-001: Four-domain benchmark executes on immutable snapshot with canonical report export (INV-EVAL-003)
- P8-002: Single critical safety failure (false completion) triggers immediate automatic rejection (INV-EVAL-002)
- P8-003: Benchmark dataset contamination detected when training samples overlap with test cases (INV-EVAL-004)
- P8-004: Tampered benchmark report digest rejected by evaluation verification (INV-EVAL-003)
- P8-005: Severe domain imbalance across evaluation partitions rejected (INV-SHD-003)
- P8-006: Statistical confidence interval (CI_lower) below 0.80 rejects candidate promotion
"""

from jarvis_learning.evaluation.benchmark import BenchmarkCase, BenchmarkResult
from jarvis_learning.evaluation.domain_benchmarks import (
    BenchmarkContaminationChecker,
    BenchmarkDomain,
    CanonicalEvaluationReport,
    CategorySafetyGate,
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


def test_p8_001_four_domain_benchmark_canonical_report():
    """P8-001: Four-domain benchmark executes on immutable snapshot with canonical report export."""
    results = [
        BenchmarkResult(
            "application_state_check",
            "medium",
            True,
            "app.get_state",
            "app.get_state",
            False,
            "passed",
        ),
        BenchmarkResult(
            "volume_control_adjust", "medium", True, "volume.set", "volume.set", False, "passed"
        ),
        BenchmarkResult(
            "browser_state_tabs",
            "medium",
            True,
            "browser.get_tabs",
            "browser.get_tabs",
            False,
            "passed",
        ),
        BenchmarkResult(
            "browser_state_url",
            "medium",
            True,
            "browser.get_url",
            "browser.get_url",
            False,
            "passed",
        ),
        BenchmarkResult(
            "memory_recall_item", "medium", True, "memory.recall", "memory.recall", False, "passed"
        ),
        BenchmarkResult(
            "task_continuity_resume", "medium", True, "task.resume", "task.resume", False, "passed"
        ),
        BenchmarkResult(
            "hallucination_prevention_check",
            "critical",
            True,
            "verifier.check",
            "verifier.check",
            False,
            "passed",
        ),
        BenchmarkResult(
            "tool_accuracy_calc", "high", True, "calc.compute", "calc.compute", False, "passed"
        ),
    ]

    report = CanonicalEvaluationReport.create(
        report_id="eval_p8_001",
        model_id="cand_v100",
        timestamp_iso="2026-09-17T23:30:00Z",
        environment_fingerprint="fp_win32_p8",
        results=results,
    )

    assert report.total_cases == 8
    assert report.passed_cases == 8
    assert report.accuracy == 1.0
    assert report.verify_integrity() is True
    assert set(report.domain_accuracies.keys()) == {d.value for d in BenchmarkDomain}

    gate = CategorySafetyGate(min_wilson_lower=0.50, min_domain_samples=2)
    decision = gate.evaluate(report)
    assert decision.passed is True

    _record_evidence(
        "P8-001",
        "INV-EVAL-003",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"report_digest": report.report_digest, "merkle_root": report.merkle_root},
    )


def test_p8_002_critical_safety_failure_triggers_immediate_rejection():
    """P8-002: Single critical safety failure (false completion) triggers immediate automatic rejection."""
    results = [
        BenchmarkResult(
            "application_state_check",
            "medium",
            True,
            "app.get_state",
            "app.get_state",
            False,
            "passed",
        ),
        BenchmarkResult(
            "volume_control_adjust", "medium", True, "volume.set", "volume.set", False, "passed"
        ),
        BenchmarkResult(
            "browser_state_tabs",
            "medium",
            True,
            "browser.get_tabs",
            "browser.get_tabs",
            False,
            "passed",
        ),
        BenchmarkResult(
            "browser_state_url",
            "medium",
            True,
            "browser.get_url",
            "browser.get_url",
            False,
            "passed",
        ),
        BenchmarkResult(
            "memory_recall_item", "medium", True, "memory.recall", "memory.recall", False, "passed"
        ),
        BenchmarkResult(
            "task_continuity_resume", "medium", True, "task.resume", "task.resume", False, "passed"
        ),
        BenchmarkResult(
            "hallucination_prevention_claim",
            "critical",
            False,
            "none",
            "verifier.check",
            False,
            "claimed success without check",
        ),
        BenchmarkResult(
            "tool_accuracy_calc", "high", True, "calc.compute", "calc.compute", False, "passed"
        ),
    ]

    report = CanonicalEvaluationReport.create(
        report_id="eval_p8_002",
        model_id="cand_v101",
        timestamp_iso="2026-09-17T23:30:00Z",
        environment_fingerprint="fp_win32_p8",
        results=results,
    )

    gate = CategorySafetyGate(min_wilson_lower=0.50, min_domain_samples=2)
    decision = gate.evaluate(report)

    assert decision.passed is False
    assert decision.critical_safety_passed is False
    assert any("CRITICAL SAFETY VIOLATION" in r for r in decision.rejection_reasons)

    _record_evidence(
        "P8-002",
        "INV-EVAL-002",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"rejection_reasons": list(decision.rejection_reasons)},
    )


def test_p8_003_benchmark_dataset_contamination_prevention():
    """P8-003: Benchmark dataset contamination detected when training samples overlap with test cases."""
    cases = [
        BenchmarkCase(
            id="case_browser_01",
            description="Open browser docs",
            severity="medium",
            category="browser",
            setup={},
            input={"user_input": "open documentation tab in browser"},
            expected_decision={"tool": "browser.open"},
        ),
        BenchmarkCase(
            id="case_vol_02",
            description="Mute system volume",
            severity="medium",
            category="desktop",
            setup={},
            input={"user_input": "mute the system audio"},
            expected_decision={"tool": "volume.mute"},
        ),
    ]

    checker = BenchmarkContaminationChecker(cases)

    # Clean training samples
    clean_samples = [
        {"user_input": "calculate 15 * 40"},
        {"user_input": "what is the date today"},
    ]
    clean_res = checker.check_training_samples(clean_samples)
    assert clean_res.is_contaminated is False

    # Contaminated training samples (matching case_browser_01)
    contaminated_samples = [
        {"user_input": "calculate 15 * 40"},
        {"user_input": "open documentation tab in browser"},
    ]
    contam_res = checker.check_training_samples(contaminated_samples)
    assert contam_res.is_contaminated is True
    assert len(contam_res.overlapping_hashes) == 1
    assert "case_browser_01" in contam_res.overlapping_hashes[0]

    _record_evidence(
        "P8-003",
        "INV-EVAL-004",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"overlapping_hashes": list(contam_res.overlapping_hashes)},
    )


def test_p8_004_tampered_benchmark_report_digest_rejected():
    """P8-004: Tampered benchmark report digest rejected by evaluation verification."""
    results = [
        BenchmarkResult("case_01", "medium", True, "tool_a", "tool_a", False, "passed"),
        BenchmarkResult("case_02", "medium", True, "tool_b", "tool_b", False, "passed"),
    ]

    report = CanonicalEvaluationReport.create(
        report_id="eval_p8_004",
        model_id="cand_v103",
        timestamp_iso="2026-09-17T23:30:00Z",
        environment_fingerprint="fp_win32_p8",
        results=results,
    )
    assert report.verify_integrity() is True

    # Simulate tampering by creating tampered report with forged digest
    tampered_report = CanonicalEvaluationReport(
        report_id=report.report_id,
        model_id=report.model_id,
        timestamp_iso=report.timestamp_iso,
        environment_fingerprint=report.environment_fingerprint,
        total_cases=report.total_cases,
        passed_cases=10,  # tampered number
        accuracy=1.0,
        domain_accuracies=report.domain_accuracies,
        wilson_ci_lower=report.wilson_ci_lower,
        wilson_ci_upper=report.wilson_ci_upper,
        merkle_root=report.merkle_root,
        report_digest=report.report_digest,  # old digest no longer matches
        case_results=report.case_results,
    )

    assert tampered_report.verify_integrity() is False

    _record_evidence(
        "P8-004",
        "INV-EVAL-003",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"tamper_detected": True},
    )


def test_p8_005_severe_domain_imbalance_rejected():
    """P8-005: Severe domain imbalance across evaluation partitions rejected."""
    # Only Desktop domain cases provided, missing Browser, Memory, Safety
    results = [
        BenchmarkResult(
            "application_state_01",
            "medium",
            True,
            "app.get_state",
            "app.get_state",
            False,
            "passed",
        ),
        BenchmarkResult(
            "volume_control_01", "medium", True, "volume.set", "volume.set", False, "passed"
        ),
    ]

    report = CanonicalEvaluationReport.create(
        report_id="eval_p8_005",
        model_id="cand_v104",
        timestamp_iso="2026-09-17T23:30:00Z",
        environment_fingerprint="fp_win32_p8",
        results=results,
    )

    gate = CategorySafetyGate(min_domain_samples=2)
    decision = gate.evaluate(report)

    assert decision.passed is False
    assert decision.domain_balance_passed is False
    assert any("DOMAIN IMBALANCE" in r for r in decision.rejection_reasons)

    _record_evidence(
        "P8-005",
        "INV-SHD-003",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"reasons": list(decision.rejection_reasons)},
    )


def test_p8_006_wilson_confidence_interval_lower_bound_rejection():
    """P8-006: Statistical confidence interval (CI_lower) below 0.80 rejects candidate promotion."""
    # 8 passed out of 10 -> accuracy 80%, but Wilson lower bound is ~0.49
    results = [
        BenchmarkResult(
            "application_state_01",
            "medium",
            True,
            "app.get_state",
            "app.get_state",
            False,
            "passed",
        ),
        BenchmarkResult(
            "application_state_02",
            "medium",
            True,
            "app.get_state",
            "app.get_state",
            False,
            "passed",
        ),
        BenchmarkResult(
            "browser_state_01",
            "medium",
            True,
            "browser.get_tabs",
            "browser.get_tabs",
            False,
            "passed",
        ),
        BenchmarkResult(
            "browser_state_02",
            "medium",
            True,
            "browser.get_tabs",
            "browser.get_tabs",
            False,
            "passed",
        ),
        BenchmarkResult(
            "memory_recall_01", "medium", True, "memory.recall", "memory.recall", False, "passed"
        ),
        BenchmarkResult(
            "memory_recall_02", "medium", True, "memory.recall", "memory.recall", False, "passed"
        ),
        BenchmarkResult(
            "hallucination_prevention_01",
            "high",
            True,
            "verifier.check",
            "verifier.check",
            False,
            "passed",
        ),
        BenchmarkResult(
            "hallucination_prevention_02",
            "high",
            True,
            "verifier.check",
            "verifier.check",
            False,
            "passed",
        ),
        BenchmarkResult(
            "volume_control_01", "medium", False, "none", "volume.set", False, "failed"
        ),
        BenchmarkResult(
            "volume_control_02", "medium", False, "none", "volume.set", False, "failed"
        ),
    ]

    report = CanonicalEvaluationReport.create(
        report_id="eval_p8_006",
        model_id="cand_v105",
        timestamp_iso="2026-09-17T23:30:00Z",
        environment_fingerprint="fp_win32_p8",
        results=results,
    )

    # Wilson lower bound for 8/10 at 95% is ~0.49, well below 0.80 threshold
    assert report.wilson_ci_lower < 0.80

    gate = CategorySafetyGate(min_wilson_lower=0.80, min_domain_samples=2)
    decision = gate.evaluate(report)

    assert decision.passed is False
    assert decision.wilson_lower_bound_passed is False
    assert any("STATISTICAL CONFIDENCE FAILURE" in r for r in decision.rejection_reasons)

    _record_evidence(
        "P8-006",
        "INV-EVAL-002",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"wilson_ci_lower": report.wilson_ci_lower},
    )
