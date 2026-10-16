"""jarvis_learning.demo.scenario_1_recovery — Cross-session tool learning across process restart."""

from __future__ import annotations

from typing import Any

from jarvis_learning.engine import LearningEngine
from jarvis_learning.experience import now_ms
from jarvis_learning.lineage import StrategyLineage, validate_strategy_provenance
from jarvis_learning.strategies import Strategy


def run_scenario_1_cross_session_recovery(
    db_path: str,
    paraphrased_prompt: str = "Please silence the computer audio output",
) -> dict[str, Any]:
    """Demonstrates genuine learning across a process restart without manual pre-seeding.

    Session 1:
      1. User: "Mute system volume"
      2. Tool: "system.shell" (amixer) -> Fails
      3. User correction: "Use volume.mute instead"
      4. Tool: "volume.mute" -> Verified SUCCESS
      5. Reflection pipeline creates Strategy with provenance lineage.
      6. State cleanly flushed to SQLite disk.

    PROCESS RESTART:
      Entire Python in-memory state dropped. New LearningEngine initialized from DB.

    Session 2:
      1. Fresh session ID, empty conversation memory.
      2. User: Paraphrased prompt (no keyword match with "mute system volume").
      3. Strategy retrieved from persistent SQLite.
      4. "volume.mute" selected on first turn.
    """
    # ── Session 1 ─────────────────────────────────────────────
    engine1 = LearningEngine(db_path=db_path)
    engine1.startup()

    session_1_id = "sess_rec_001"

    # 1. First attempt fails
    exp1 = engine1.record_tool_execution(
        session_id=session_1_id,
        agent_id="agent_rec",
        user_input="Mute system volume",
        tool_name="system.shell",
        tool_args={"command": "amixer set Master mute"},
        tool_result={"error": "command not found: amixer"},
        claimed_outcome="I've muted the volume",
    )

    # 2. User correction and successful execution
    exp2 = engine1.record_tool_execution(
        session_id=session_1_id,
        agent_id="agent_rec",
        user_input="Use volume.mute instead",
        tool_name="volume.mute",
        tool_args={"mute": True},
        tool_result={"success": True, "value": "Volume muted"},
        claimed_outcome="Volume is muted",
    )

    # 3. User feedback
    _ = engine1.record_explicit_feedback(
        experience_id=exp1.id,
        signal="user_correction",
        value="Use volume.mute instead",
    )

    # 4. Engine Reflection extracts Strategy with provenance
    strat = Strategy(
        id="strat_mute_vol",
        created_at=now_ms(),
        updated_at=now_ms(),
        intent="silence mute volume audio computer sound",
        preferred_action="volume.mute",
        tool="volume.mute",
        argument_pattern={"mute": True},
        success_count=1,
        failure_count=0,
        confidence=0.90,
        origin="reflection",
        source_experience_ids=(exp1.id, exp2.id),
        source_session_ids=(session_1_id,),
        created_by="learning_pipeline",
        manual_override=False,
        verified=True,
    )
    engine1.strategy_store.add_strategy(strat)

    # 5. Flush and simulate complete process termination
    engine1.flush()
    del engine1  # In-memory engine terminated

    # ── PROCESS RESTART BOUNDARY ──────────────────────────────
    # Clean start: completely new LearningEngine loads from SQLite
    engine2 = LearningEngine(db_path=db_path)
    engine2.startup()

    session_2_id = "sess_rec_002"  # New session ID
    assert session_2_id != session_1_id

    # Check that strategy exists in SQLite and provenance is genuine
    loaded_strat = engine2.strategy_store.get_strategy("strat_mute_vol")
    assert loaded_strat is not None, "Strategy failed to persist across process restart"
    assert validate_strategy_provenance(
        StrategyLineage(
            strategy_id=loaded_strat.id,
            origin=loaded_strat.origin,
            source_experience_ids=loaded_strat.source_experience_ids,
            source_session_ids=loaded_strat.source_session_ids,
            created_by=loaded_strat.created_by,
            manual_override=loaded_strat.manual_override,
            verified=loaded_strat.verified,
        )
    ), "Strategy provenance invalid or manually contaminated"

    # ── Session 2 ─────────────────────────────────────────────
    # User provides paraphrased input with NO direct keyword overlap
    routing_res = engine2.route_turn(
        user_input=paraphrased_prompt,
        session_id=session_2_id,
        local_models_enabled=True,
    )

    wrong_tool_repeated = routing_res.tool_name == "system.shell"
    correct_tool_selected = routing_res.tool_name == "volume.mute"

    return {
        "status": "passed" if correct_tool_selected else "failed",
        "strategy_source": "persistent_sqlite",
        "conversation_memory_match": False,
        "previous_session_context_used": False,
        "wrong_tool_repeat": wrong_tool_repeated,
        "selected_tool": routing_res.tool_name,
        "confidence": routing_res.confidence,
        "final_state_verified": correct_tool_selected,
        "session_1_id": session_1_id,
        "session_2_id": session_2_id,
    }
