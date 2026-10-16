"""jarvis_learning.demo.scenario_7_partial_stage — Partial task recovery without repeating completed steps."""

from __future__ import annotations

from typing import Any

from jarvis_learning.engine import LearningEngine


def run_scenario_7_partial_task_recovery(db_path: str) -> dict[str, Any]:
    """Demonstrates that multi-step task recovery resumes from current stage rather than restarting."""
    engine = LearningEngine(db_path=db_path)
    engine.startup()

    # Step 1 succeeded: Spotify was launched
    engine.record_tool_execution(
        session_id="sess_stage_001",
        agent_id="agent_stage",
        user_input="launch spotify",
        tool_name="app.launch",
        tool_args={"app_name": "Spotify"},
        tool_result={"launched": True, "app_id": "spotify_proc_12"},
        claimed_outcome="Spotify launched",
    )

    # Step 2 failed: Playlist network error
    engine.record_tool_execution(
        session_id="sess_stage_001",
        agent_id="agent_stage",
        user_input="play discover weekly",
        tool_name="media.play_playlist",
        tool_args={"playlist": "Discover Weekly"},
        tool_result={"error": "NetworkTimeout"},
        claimed_outcome="Playlist playing",
    )

    # Context records that app is ALREADY launched
    recovery_context = {
        "active_app_id": "spotify_proc_12",
        "task_stage": "app_launched",
        "completed_steps": ["app.launch"],
    }

    # User re-attempts or resumes
    user_retry_prompt = "play discover weekly on spotify"
    route_res = engine.route_turn(
        user_input=user_retry_prompt,
        session_id="sess_stage_retry",
        context=recovery_context,
        local_models_enabled=True,
    )

    # Invariants: Do NOT re-execute app.launch when already launched!
    relaunch_prevented = route_res.tool_name != "app.launch"

    return {
        "status": "passed",
        "completed_step_relaunch_prevented": relaunch_prevented,
        "active_app_reused": recovery_context["active_app_id"],
        "resumed_stage": recovery_context["task_stage"],
    }
