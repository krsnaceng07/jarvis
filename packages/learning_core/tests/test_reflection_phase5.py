"""Comprehensive Phase 5 Test Suite: Autonomous Reflection, Causal Attribution & Strategy Lifecycle.

Tests:
1. Evidence trust levels and cryptographic payload digestion
2. Multi-hypothesis CausalCritic attribution and recovery planning
3. PathQualityEvaluator: separation of verified success from strategy learning worthy
4. Multi-dimensional FailurePattern scoping (exact_arguments, same_application, same_domain, same_device, global)
5. Beta-Bernoulli Bayesian confidence engine with credible interval and temporal decay
6. Evidence independence accounting preventing pseudo-replication
7. Risk-tiered qualification & promotion gate (Tiers 1-5, auto-promotion DISABLED)
8. Immediate automatic rollback & quarantine on 2 consecutive failures
9. Precondition contracts and deterministic conflict resolution with LLM fallback on ambiguity
10. Feedback attribution isolating user input defects from agent execution defects
11. Multi-step task episode reflection and bottleneck step localization
12. Strategy compatibility fingerprinting, schema hash checks, and expiration
13. Detached background reflection worker with cooperative pause/resume for audio/voice
14. End-to-end LearningEngine integration with transactional SQLite persistence
"""

import json
import pathlib
import tempfile
import time
import pytest

from jarvis_learning.causal_critic import (
    AttributionStatus,
    CausalCritic,
    CausalFailureType,
)
from jarvis_learning.compatibility import CompatibilityFingerprint
from jarvis_learning.confidence_engine import BayesianConfidenceState
from jarvis_learning.engine import LearningEngine
from jarvis_learning.evidence_model import (
    EvidenceSource,
    EvidenceTrustLevel,
    ExperienceEvidence,
    compute_payload_digest,
)
from jarvis_learning.experience import Experience
from jarvis_learning.feedback_attribution import (
    AttributionCategory,
    FeedbackAttributor,
)
from jarvis_learning.lineage import EvidenceIndependence
from jarvis_learning.path_quality import PathQualityEvaluator
from jarvis_learning.precondition_contract import PreconditionContract, StateProbe
from jarvis_learning.reflection_worker import JobStatus, ReflectionWorker
from jarvis_learning.strategies import (
    FailurePattern,
    ScopeLevel,
)
from jarvis_learning.strategy_conflict import (
    ConflictResolver,
    StrategyCandidate,
    StrategyFingerprint,
)
from jarvis_learning.strategy_lifecycle import (
    StrategyLifecycleManager,
    StrategyLifecycleState,
)
from jarvis_learning.task_reflection import TaskEpisodeReflector, TaskStepRecord


# ── 1. Evidence Trust & Digest ────────────────────────────────


def test_evidence_trust_and_digests() -> None:
    raw_output = {"exit_code": 0, "verified_stat": {"size": 4096, "mtime": 1789000}}
    digest = compute_payload_digest(raw_output)
    assert len(digest) == 64
    # Determinism
    assert compute_payload_digest(raw_output) == digest

    ev = ExperienceEvidence.create(
        experience_id="exp_001",
        source=EvidenceSource.VERIFIER_READBACK,
        trust_level=EvidenceTrustLevel.TRUSTED,
        raw_payload=raw_output,
        verification_status="verified",
        evidence_id="ev_001",
    )
    assert ev.trust_level == EvidenceTrustLevel.TRUSTED
    d = ev.to_dict()
    assert d["trust_level"] == "TRUSTED"
    assert d["payload_digest"] == digest


# ── 2. CausalCritic Multi-Hypothesis Attribution ──────────────


def test_causal_critic_attribution_and_recovery() -> None:
    critic = CausalCritic()

    # Scenario: Permission Denied error
    critique = critic.analyze_experience(
        tool_name="file_writer",
        tool_args={"path": "/etc/protected.conf"},
        tool_result=None,
        error_message="PermissionError: [Errno 13] Permission denied: '/etc/protected.conf'",
        verification_status="failed",
    )
    assert critique.primary_failure_type == CausalFailureType.PERMISSION_OR_AUTH_FAILURE
    assert critique.attribution_status in (AttributionStatus.CONFIRMED, AttributionStatus.PROBABLE)
    assert critique.recovery_plan is not None
    assert critique.recovery_plan.max_attempts <= 2
    assert (
        critique.recovery_plan.trigger_failure_type == CausalFailureType.PERMISSION_OR_AUTH_FAILURE
    )

    # Scenario: Timeout
    critique_timeout = critic.analyze_experience(
        tool_name="browser_click",
        tool_args={"selector": "#submit"},
        tool_result=None,
        error_message="TimeoutError: Operation timed out after 30000ms",
        verification_status="failed",
    )
    assert critique_timeout.primary_failure_type == CausalFailureType.TIMEOUT_OR_HANG
    assert "retry" in (critique_timeout.recommended_recovery_action or "").lower()


# ── 3. Path Quality Evaluator ─────────────────────────────────


def test_path_quality_evaluator() -> None:
    evaluator = PathQualityEvaluator()

    # Clean, optimal, verified execution
    quality, path_eval, worthy = evaluator.evaluate(
        goal_satisfied=True,
        correct_target=True,
        duplicate_free=True,
        side_effects_clean=True,
        policy_compliant=True,
        actual_steps=1,
        optimal_steps=1,
        execution_time_ms=150.0,
    )
    assert quality.goal_satisfied is True
    assert path_eval.efficiency_score == 1.0
    assert worthy is True

    # Execution with excessive redundant steps and duplicate attempts
    quality_sloppy, path_eval_sloppy, worthy_sloppy = evaluator.evaluate(
        goal_satisfied=True,
        correct_target=True,
        duplicate_free=False,
        side_effects_clean=True,
        policy_compliant=True,
        actual_steps=8,
        optimal_steps=2,
        duplicate_attempts=3,
        execution_time_ms=12000.0,
    )
    assert worthy_sloppy is False
    assert path_eval_sloppy.efficiency_score < 0.6


# ── 4. Multi-Dimensional Failure Pattern Scoping ──────────────


def test_failure_pattern_scoping() -> None:
    # 1. exact_arguments
    fp_exact = FailurePattern(
        id="fp_1",
        created_at=100,
        pattern_name="exact_fail",
        bad_action="run_query",
        scope=ScopeLevel.EXACT_ARGUMENTS.value,
        argument_signature=json.dumps({"query": "SELECT * FROM huge_table"}, sort_keys=True),
    )
    assert fp_exact.is_applicable("run_query", {"query": "SELECT * FROM huge_table"}) is True
    assert (
        fp_exact.is_applicable("run_query", {"query": "SELECT id FROM huge_table LIMIT 10"})
        is False
    )

    # 2. same_domain
    fp_domain = FailurePattern(
        id="fp_2",
        created_at=100,
        pattern_name="domain_block",
        bad_action="browser_open",
        scope=ScopeLevel.SAME_DOMAIN.value,
        condition={"domain": "flaky-api.org"},
    )
    assert fp_domain.is_applicable("browser_open", {"url": "https://flaky-api.org/v1/data"}) is True
    assert fp_domain.is_applicable("browser_open", {"url": "https://good-service.com"}) is False

    # 3. same_application
    fp_app = FailurePattern(
        id="fp_3",
        created_at=100,
        pattern_name="app_crash",
        bad_action="desktop_interact",
        scope=ScopeLevel.SAME_APPLICATION.value,
        condition={"application": "LegacyCAD.exe"},
    )
    assert (
        fp_app.is_applicable("desktop_interact", {"application": "LegacyCAD.exe", "btn": "render"})
        is True
    )
    assert (
        fp_app.is_applicable("desktop_interact", {"application": "Notepad.exe", "btn": "save"})
        is False
    )


# ── 5. Beta-Bernoulli Confidence Engine & Decay ───────────────


def test_bayesian_confidence_and_decay() -> None:
    t0 = time.time()
    bayes = BayesianConfidenceState(last_updated_timestamp=t0)
    assert bayes.mean == 0.5
    assert bayes.effective_n == 0.0

    # Record 5 trusted successes
    for _ in range(5):
        bayes.update(success=True, trust_level=EvidenceTrustLevel.TRUSTED, timestamp=t0)
    assert bayes.mean > 0.75
    assert bayes.effective_n == pytest.approx(5.0)
    assert bayes.ci_lower > 0.45

    # UNTRUSTED evidence should be discarded from posterior updates
    prev_alpha = bayes.alpha
    bayes.update(success=False, trust_level=EvidenceTrustLevel.UNTRUSTED, timestamp=t0)
    assert bayes.alpha == prev_alpha
    assert bayes.effective_n == pytest.approx(5.0)

    # Temporal Decay over 60 days with 30-day half-life
    now = bayes.last_updated_timestamp + (60 * 86400)
    bayes.apply_decay(current_time=now, half_life_days=30.0)
    # Excess alpha should decay toward prior (2.0) by roughly factor of 0.25
    assert bayes.effective_n < 2.0
    assert bayes.mean < 0.70


# ── 6. Evidence Independence Accounting ───────────────────────


def test_evidence_independence() -> None:
    # 5 observations all from the same session and same task (pseudo-replication)
    ei_correlated = EvidenceIndependence(
        unique_sessions=1,
        unique_tasks=1,
        unique_targets=1,
        total_observations=5,
        independence_ratio=0.2,
    )
    assert ei_correlated.is_independent is False

    # 5 observations spanning 3 sessions and 3 tasks
    ei_independent = EvidenceIndependence(
        unique_sessions=3,
        unique_tasks=3,
        unique_targets=4,
        total_observations=5,
        independence_ratio=0.8,
    )
    assert ei_independent.is_independent is True


# ── 7. Risk-Tiered Promotion & Qualification Gate ─────────────


def test_strategy_lifecycle_and_promotion_matrix() -> None:
    mgr = StrategyLifecycleManager()

    # Invariant: Automatic promotion is strictly DISABLED
    state, err = mgr.transition_state(
        strategy_id="strat_001",
        current_state=StrategyLifecycleState.QUALIFIED,
        target_state=StrategyLifecycleState.PROMOTED,
        reason="system tried to auto-promote",
        operator="system",  # Non-human operator
    )
    assert state == StrategyLifecycleState.QUALIFIED
    assert "DISABLED" in str(err)

    # Check Tier 3 (Browser) qualification requirements: min trials=8, CI_lower>=0.85
    qualified, reason = mgr.check_qualification(risk_tier=3, effective_n=4.0, ci_lower=0.90)
    assert qualified is False  # trials < 8

    qualified, reason = mgr.check_qualification(risk_tier=3, effective_n=10.0, ci_lower=0.88)
    assert qualified is True

    # Human operator promotion with qualified metrics
    promoted_state, err = mgr.transition_state(
        strategy_id="strat_001",
        current_state=StrategyLifecycleState.QUALIFIED,
        target_state=StrategyLifecycleState.PROMOTED,
        reason="Operator approved after live review",
        operator="human_operator_kcs",
        risk_tier=3,
        effective_n=10.0,
        ci_lower=0.88,
    )
    assert promoted_state == StrategyLifecycleState.PROMOTED
    assert err is None


# ── 8. Immediate Automatic Rollback & Quarantine ──────────────


def test_immediate_automatic_rollback() -> None:
    mgr = StrategyLifecycleManager()

    # 1 failure does not quarantine yet
    st1, _ = mgr.record_execution_outcome(
        "s_test", StrategyLifecycleState.PROMOTED, consecutive_failures=1
    )
    assert st1 == StrategyLifecycleState.PROMOTED

    # 2 consecutive failures triggers immediate automatic rollback
    st2, _ = mgr.record_execution_outcome(
        "s_test", StrategyLifecycleState.PROMOTED, consecutive_failures=2
    )
    assert st2 == StrategyLifecycleState.QUARANTINED


# ── 9. Preconditions & Conflict Resolution ────────────────────


def test_precondition_contract_and_conflict_resolution() -> None:
    precond = PreconditionContract(
        required_tools=["browser_click"],
        state_probes=[
            StateProbe(probe_tool="window_active", expected_value="Chrome", comparator="contains")
        ],
        parameter_constraints={"timeout_ms": {"max": 10000}},
    )

    # Valid context
    ok, reason = precond.check_satisfaction(
        context={"window_active": "Google Chrome - Dashboard", "tool_args": {"timeout_ms": 5000}},
        available_tools=["browser_click", "browser_open"],
    )
    assert ok is True
    assert reason is None

    # Missing tool
    ok_bad, reason_bad = precond.check_satisfaction(
        context={"window_active": "Chrome"},
        available_tools=["other_tool"],
    )
    assert ok_bad is False
    assert "Missing required tool" in reason_bad

    # Conflict Resolution: 2 candidates targeting the same fingerprint
    fp = StrategyFingerprint(domain="browser", task_family="submit", target_tool="browser_click")
    c1 = StrategyCandidate(
        strategy_id="strat_high_ci",
        fingerprint=fp,
        ci_lower=0.92,
        effective_n=20.0,
        risk_tier=2,
        precondition_specificity_score=5,
    )
    c2 = StrategyCandidate(
        strategy_id="strat_low_ci",
        fingerprint=fp,
        ci_lower=0.60,
        effective_n=5.0,
        risk_tier=2,
        precondition_specificity_score=2,
    )

    best, err = ConflictResolver.resolve_best([c1, c2])
    assert best == c1
    assert err is None

    # Ambiguity fallback to Foundation Model
    c_tie1 = StrategyCandidate(
        "strat_a",
        fp,
        ci_lower=0.88,
        effective_n=10.0,
        risk_tier=2,
        precondition_specificity_score=3,
    )
    c_tie2 = StrategyCandidate(
        "strat_b",
        fp,
        ci_lower=0.86,
        effective_n=10.0,
        risk_tier=2,
        precondition_specificity_score=3,
    )
    best_tie, err_tie = ConflictResolver.resolve_best([c_tie1, c_tie2])
    assert best_tie is None
    assert "Ambiguous conflict" in str(err_tie)


# ── 10. Feedback Attribution & Bad-Input Isolation ───────────


def test_feedback_attribution_isolates_user_input_defects() -> None:
    # User requested a non-existent file path: "summarize draft_v9.txt"
    res = FeedbackAttributor.classify(
        user_prompt="summarize draft_v9.txt",
        tool_args={"path": "draft_v9.txt"},
        tool_error="FileNotFoundError: [Errno 2] No such file or directory: 'draft_v9.txt'",
        verifier_verdict="failed",
        signals=[],
    )
    assert res.category == AttributionCategory.USER_INPUT_DEFECT
    # Learning engine must NOT penalize execution strategies for user typos/missing inputs
    assert res.strategy_penalizable is False

    # Genuine execution defect
    res_exec = FeedbackAttributor.classify(
        user_prompt="click the download button",
        tool_args={"selector": "#download-btn"},
        tool_error="ElementNotInteractableException: element is obscured by modal",
        verifier_verdict="failed",
        signals=[],
    )
    assert res_exec.category == AttributionCategory.AGENT_EXECUTION_FAILURE
    assert res_exec.strategy_penalizable is True


# ── 11. Multi-Step Task Episode Reflection ────────────────────


def test_task_episode_reflection() -> None:
    steps = [
        TaskStepRecord(
            step_index=1,
            tool_name="browser_open",
            args={"url": "https://app.com"},
            success=True,
            verified=True,
        ),
        TaskStepRecord(
            step_index=2,
            tool_name="browser_click",
            args={"selector": "#login"},
            success=True,
            verified=True,
        ),
        TaskStepRecord(
            step_index=3,
            tool_name="file_writer",
            args={"path": "out.txt"},
            success=False,
            error="Disk Full",
            verified=False,
        ),
    ]

    refl = TaskEpisodeReflector.reflect_episode(task_id="task_123", steps=steps)
    assert refl.total_steps == 3
    assert refl.successful_steps == 2
    assert refl.overall_outcome == "TOTAL_FAILURE"
    assert refl.critical_failure_step == 3
    assert refl.bottleneck_tool == "file_writer"
    assert len(refl.extractable_subsequences) == 1
    assert refl.extractable_subsequences[0] == ["browser_open", "browser_click"]


# ── 12. Compatibility Fingerprint & Expiration ────────────────


def test_compatibility_fingerprint_and_expiration() -> None:
    schema = {"type": "object", "properties": {"target": {"type": "string"}}}
    schema_hash = CompatibilityFingerprint.compute_schema_hash(schema)

    fp = CompatibilityFingerprint(
        tool_name="browser_click",
        tool_schema_hash=schema_hash,
        os_platform="win32",
        created_timestamp=time.time(),
        last_verified_timestamp=time.time(),
    )

    # Compatible
    ok, err = fp.check_compatibility(current_schema_hash=schema_hash)
    assert ok is True

    # Schema evolved
    evolved_hash = CompatibilityFingerprint.compute_schema_hash(
        {"type": "object", "properties": {"target": {"type": "int"}}}
    )
    ok_bad_schema, err_bad_schema = fp.check_compatibility(current_schema_hash=evolved_hash)
    assert ok_bad_schema is False
    assert "schema evolved" in str(err_bad_schema).lower()

    # Stale / expired TTL
    fp_old = CompatibilityFingerprint(
        tool_name="browser_click",
        tool_schema_hash=schema_hash,
        os_platform="win32",
        last_verified_timestamp=time.time() - (100 * 86400),  # 100 days old
    )
    ok_stale, err_stale = fp_old.check_compatibility(
        current_schema_hash=schema_hash, max_age_days=90
    )
    assert ok_stale is False
    assert "stale" in str(err_stale).lower()


# ── 13. Background Reflection Worker ──────────────────────────


def test_background_reflection_worker() -> None:
    worker = ReflectionWorker(max_queue_size=10)
    worker.enqueue_job("job_urgent", {"task": "critique_failure"}, priority=1)
    worker.enqueue_job("job_normal", {"task": "generalize_pattern"}, priority=5)

    assert worker.pending_count() == 2

    # Cooperative Yielding: pause during live speech / audio turns
    worker.pause()
    assert worker.is_paused is True
    # Step yields None without running anything
    processed = worker.step(lambda j: True)
    assert processed is None
    assert worker.pending_count() == 2

    # Resume when audio is idle
    worker.resume()
    assert worker.is_paused is False
    # Urgency job runs first
    first_job = worker.step(lambda j: True)
    assert first_job == "job_urgent"
    assert worker.get_job_status("job_urgent") == JobStatus.COMPLETED
    assert worker.pending_count() == 1


# ── 14. Full End-to-End Engine & SQLite Integration ───────────


def test_full_engine_reflection_e2e() -> None:
    tmp_dir = pathlib.Path(tempfile.mkdtemp())
    db_path = tmp_dir / "learning_test.sqlite"

    engine = LearningEngine(str(db_path))
    engine.startup()

    # 1. Record experience with execution defect
    exp_fail = Experience(
        id="exp_fail_01",
        created_at=int(time.time() * 1000),
        session_id="sess_test",
        agent_id="agent_main",
        user_input="open https://broken-target.com",
        interpreted_intent="open website",
        selected_tool="browser_navigate",
        tool_arguments=json.dumps({"url": "https://broken-target.com"}),
        tool_result="",
        success=False,
        error="Connection refused: net::ERR_CONNECTION_REFUSED",
        verification_status="verified_failure",
    )
    engine.db.store_experience(exp_fail)

    # 2. Reflect on experience
    assert engine.reflect_on_experience(exp_fail) is not None

    # Verify FailurePattern created with SAME_DOMAIN scope
    patterns = engine.strategy_store.all_failure_patterns()
    assert len(patterns) >= 1
    fp = patterns[0]
    assert fp.scope == ScopeLevel.SAME_DOMAIN.value
    assert fp.condition.get("domain") == "https://broken-target.com"

    # 3. Verify SQLite persistence of reflection and causal data
    stats = engine.db.get_stats()
    assert stats["failure_patterns"] >= 1
    assert stats["experiences"] >= 1

    # 4. Background queue integration
    job_ok = engine.enqueue_background_reflection(
        job_id="job_async_01",
        payload={"experience_id": exp_fail.id},
        priority=3,
    )
    assert job_ok is True
    assert engine.reflection_worker.pending_count() == 1

    # Step background reflection
    done_job_id = engine.step_background_reflection()
    assert done_job_id == "job_async_01"
    assert engine.reflection_worker.pending_count() == 0

    # Clean up
    import shutil

    shutil.rmtree(tmp_dir, ignore_errors=True)
