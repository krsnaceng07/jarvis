"""jarvis_learning.demo.scenario_2_failure — Scoped synthetic harmless failure pattern avoidance."""

from __future__ import annotations

import json
from typing import Any

from jarvis_learning.engine import LearningEngine
from jarvis_learning.experience import now_ms
from jarvis_learning.strategies import FailurePattern


def run_scenario_2_failure_avoidance(db_path: str) -> dict[str, Any]:
    """Demonstrates safe failure pattern learning without executing dangerous commands.

    Session 1:
      Attempting to read a known missing test file returns FILE_NOT_FOUND.
      Engine records scoped FailurePattern for that exact path.

    Session 2:
      1. Requesting the same missing path is detected and avoided.
      2. Requesting a valid different path is NOT blocked (context-sensitive scope).
    """
    engine = LearningEngine(db_path=db_path)
    engine.startup()

    missing_path = "/tmp/test_workspace/missing_artifact.json"
    valid_path = "/tmp/test_workspace/existing_document.txt"

    # ── Session 1: Harmless failure observation ───────────────
    _ = engine.record_tool_execution(
        session_id="sess_fail_001",
        agent_id="agent_fail",
        user_input="read missing artifact",
        tool_name="filesystem.read",
        tool_args={"path": missing_path},
        tool_result={"error": "FileNotFoundError", "path": missing_path},
        claimed_outcome="File read successfully",
    )

    # Scoped failure pattern
    pat = FailurePattern(
        id="pat_missing_file_001",
        created_at=now_ms(),
        pattern_name="avoid_missing_test_artifact",
        condition={"path": missing_path},
        bad_action="filesystem.read",
        preferred_action="filesystem.search",
        occurrence_count=1,
        confidence=0.85,
        scope="exact_arguments",
        recovery_strategy="ask_clarification",
        tool_name="filesystem.read",
        argument_signature=json.dumps({"path": missing_path}, sort_keys=True),
    )
    engine.strategy_store.add_failure_pattern(pat)

    # ── Session 2: Fresh checks ───────────────────────────────
    # Case A: Repeated exact bad call is detected
    blocked_patterns = engine.strategy_store.find_failure_patterns_for_action(
        "filesystem.read", tool_args={"path": missing_path}
    )
    assert len(blocked_patterns) == 1, "Failed to detect scoped failure pattern"
    assert blocked_patterns[0].preferred_action == "filesystem.search"

    # Case B: Valid path call is NOT blocked
    allowed_patterns = engine.strategy_store.find_failure_patterns_for_action(
        "filesystem.read", tool_args={"path": valid_path}
    )
    assert len(allowed_patterns) == 0, "Failure pattern over-generalized and blocked valid path!"

    return {
        "status": "passed",
        "scoped_avoidance_working": True,
        "overgeneralization_prevented": True,
        "dangerous_command_executed": False,
    }
