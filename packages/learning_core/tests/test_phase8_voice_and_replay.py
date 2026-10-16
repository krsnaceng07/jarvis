"""Phase 8 Operational Acceptance Suite 5: Behavioral & Voice Safety.

Scenarios:
- P8-029: Barge-in voice interruption cancels pending tool call within 150ms TTS stop latency without orphan state (INV-VOICE-001)
- P8-030: Multi-turn user correction successfully redirects task goal without false completion claims (INV-CORR-001)
"""

from jarvis_learning.evaluation.invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    OperationalTestEvidence,
    TestExecutionClassification,
)
from jarvis_learning.evaluation.voice_evaluator import (
    CancellationToken,
    CorrectionEvaluationHarness,
    TaskGenerationContext,
    VoiceInterruptionHarness,
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


def test_p8_029_voice_barge_in_cancellation_latency_and_commit_guard():
    """P8-029: Barge-in voice interruption cancels pending tool call within 150ms TTS stop latency without orphan state."""
    harness = VoiceInterruptionHarness(max_allowed_stop_latency_ms=150.0)
    token = CancellationToken()

    state = {"system_volume": 50, "committed": False}

    def tool_fn():
        # Simulated tool execution returning new volume
        return 90

    def commit_fn(val):
        state["system_volume"] = val
        state["committed"] = True

    # Run simulation with barge-in interruption before commit
    res = harness.simulate_barge_in(token, tool_fn, commit_fn)

    assert res["cancelled"] is True
    assert res["latency_compliant"] is True
    assert res["stop_latency_ms"] <= 150.0
    assert res["commit_performed"] is False
    assert res["commit_blocked_safely"] is True
    assert state["committed"] is False
    assert state["system_volume"] == 50  # State unchanged

    _record_evidence(
        "P8-029",
        "INV-VOICE-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"stop_latency_ms": res["stop_latency_ms"], "commit_blocked": res["commit_blocked_safely"]},
    )


def test_p8_030_user_correction_task_generation_redirection():
    """P8-030: Multi-turn user correction successfully redirects task goal without false completion claims."""
    harness = CorrectionEvaluationHarness()
    context = TaskGenerationContext(current_generation=1, task_goal="Open window A")

    stale_pending_actions = [
        {
            "action_id": "act_1",
            "generation": 1,
            "tool": "window.focus",
            "args": {"title": "Window A"},
        },
        {"action_id": "act_2", "generation": 1, "tool": "window.maximize", "args": {}},
    ]

    new_action = {
        "action_id": "act_3",
        "generation": 2,
        "tool": "window.focus",
        "args": {"title": "Window B"},
    }

    res = harness.evaluate_correction(
        context=context,
        correction_input="No, I meant the other window (Window B)",
        new_goal="Open window B",
        stale_actions=stale_pending_actions,
        new_action=new_action,
    )

    assert res["new_generation"] == 2
    assert res["discarded_stale_count"] == 2
    assert res["all_stale_discarded"] is True
    assert res["new_action_accepted"] is True
    assert context.task_goal == "Open window B"

    _record_evidence(
        "P8-030",
        "INV-CORR-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"new_generation": res["new_generation"], "discarded_stale": res["discarded_stale_count"]},
    )
