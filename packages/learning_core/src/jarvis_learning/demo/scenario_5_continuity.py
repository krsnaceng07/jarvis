"""jarvis_learning.demo.scenario_5_continuity — Workspace state continuity & YouTube tab reuse."""

from __future__ import annotations

from typing import Any

from jarvis_learning.engine import LearningEngine
from jarvis_learning.strategies import Strategy, now_ms


def run_scenario_5_workspace_continuity(db_path: str) -> dict[str, Any]:
    """Demonstrates multi-turn stage-aware task continuity and browser tab reuse."""
    engine = LearningEngine(db_path=db_path)
    engine.startup()

    # Pre-register verified strategies
    s_search = Strategy(
        id="strat_yt_search",
        created_at=now_ms(),
        updated_at=now_ms(),
        intent="search youtube music video",
        preferred_action="browser.search",
        tool="browser.search",
        argument_pattern={"query": ""},
        confidence=0.90,
    )
    s_play = Strategy(
        id="strat_yt_play",
        created_at=now_ms(),
        updated_at=now_ms(),
        intent="play music video song",
        preferred_action="browser.click",
        tool="browser.click",
        argument_pattern={"selector": ".first-video"},
        confidence=0.90,
    )
    engine.strategy_store.add_strategy(s_search)
    engine.strategy_store.add_strategy(s_play)

    # ── Turn 1: Initial state established ─────────────────────
    active_target_id = "target_tab_yt_99"
    workspace_context = {
        "active_browser_target_id": active_target_id,
        "task_stage": "youtube_open",
    }

    # ── Turn 2: User says "Search for lo-fi music" ─────────────
    res_turn2 = engine.route_turn(
        user_input="search youtube music video for lo-fi",
        session_id="sess_cont_001",
        context=workspace_context,
        local_models_enabled=True,
    )

    assert res_turn2.task_continuity_applied is True, (
        "Router failed to recognize ongoing task continuity"
    )
    assert res_turn2.tool_arguments.get("target_id") == active_target_id, (
        "Router failed to reuse existing browser tab target"
    )

    # ── Turn 3: User says "Play the first song" ───────────────
    workspace_context["task_stage"] = "youtube_searched"
    res_turn3 = engine.route_turn(
        user_input="play music video song",
        session_id="sess_cont_001",
        context=workspace_context,
        local_models_enabled=True,
    )

    assert res_turn3.task_continuity_applied is True
    assert res_turn3.tool_arguments.get("target_id") == active_target_id

    return {
        "status": "passed",
        "existing_tab_reused": True,
        "duplicate_tabs_prevented": True,
        "target_id": active_target_id,
        "turn2_tool": res_turn2.tool_name,
        "turn3_tool": res_turn3.tool_name,
    }
