"""jarvis_learning.demo — End-to-end learning demonstrations, controls, and proofs."""

from __future__ import annotations

from jarvis_learning.demo.controls import (
    ControlArm,
    ControlArmResult,
    assess_learning_effect,
    execute_turn_with_arm,
)
from jarvis_learning.demo.scenario_1_recovery import run_scenario_1_cross_session_recovery
from jarvis_learning.demo.scenario_2_failure import run_scenario_2_failure_avoidance
from jarvis_learning.demo.scenario_3_shadow_promo import run_scenario_3_shadow_qualification
from jarvis_learning.demo.scenario_4_rollback import run_scenario_4_classified_rollback
from jarvis_learning.demo.scenario_5_continuity import run_scenario_5_workspace_continuity
from jarvis_learning.demo.scenario_6_restart import run_scenario_6_persistent_reload
from jarvis_learning.demo.scenario_7_partial_stage import run_scenario_7_partial_task_recovery
from jarvis_learning.demo.scenario_8_truthful_state import run_scenario_8_truthful_reporting

__all__ = [
    "ControlArm",
    "ControlArmResult",
    "assess_learning_effect",
    "execute_turn_with_arm",
    "run_scenario_1_cross_session_recovery",
    "run_scenario_2_failure_avoidance",
    "run_scenario_3_shadow_qualification",
    "run_scenario_4_classified_rollback",
    "run_scenario_5_workspace_continuity",
    "run_scenario_6_persistent_reload",
    "run_scenario_7_partial_task_recovery",
    "run_scenario_8_truthful_reporting",
]
