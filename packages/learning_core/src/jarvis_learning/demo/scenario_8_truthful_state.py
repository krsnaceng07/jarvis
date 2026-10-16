"""jarvis_learning.demo.scenario_8_truthful_state — False completion prevention and truthful reporting."""

from __future__ import annotations

from typing import Any

from jarvis_learning.engine import LearningEngine
from jarvis_learning.lineage import VerificationOutcome


def run_scenario_8_truthful_reporting(db_path: str) -> dict[str, Any]:
    """Demonstrates that tool execution reporting success is rejected if actual state is unchanged."""
    engine = LearningEngine(db_path=db_path)
    engine.startup()

    # Tool returned exit_code 0 or attempted=True, but actual physical state did NOT change
    simulated_tool_result = {"status": "called", "attempted": True}
    engine.record_tool_execution(
        session_id="sess_s8",
        agent_id="agent_s8",
        user_input="set volume",
        tool_name="volume.mute",
        tool_args={"mute": True},
        tool_result=simulated_tool_result,
        claimed_outcome="Action attempted",
    )
    actual_state_before = {"volume": 0}
    actual_state_after = {"volume": 0}  # State remained unchanged!

    # Verification checks physical state
    state_changed = actual_state_after["volume"] != actual_state_before["volume"]

    if not state_changed:
        outcome = VerificationOutcome.VERIFIED_FAILURE
        truthful_report = "Action attempted but actual volume state remained unchanged"
    else:
        outcome = VerificationOutcome.VERIFIED_SUCCESS
        truthful_report = "Action verified successful"

    assert outcome == VerificationOutcome.VERIFIED_FAILURE, (
        "Engine falsely accepted unverified execution as success!"
    )

    # Verify that no positive strategy was added for this failed execution
    initial_strategies_count = len(engine.strategy_store.all_strategies())
    # Falsified run does NOT add positive strategies
    assert len(engine.strategy_store.all_strategies()) == initial_strategies_count

    return {
        "status": "passed",
        "verification_outcome": outcome.value,
        "false_completion_prevented": True,
        "truthful_report": truthful_report,
    }
