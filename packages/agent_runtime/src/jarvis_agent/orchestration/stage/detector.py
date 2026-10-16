"""Multi-factor StageDetector with strict 9-level deterministic precedence."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from jarvis_agent.orchestration.models import (
    ApprovalStatus,
    NodeStatus,
    PlanDAG,
    Task,
    TaskStage,
    UserTurn,
)
from jarvis_agent.orchestration.state.reducer import RuntimeState


@dataclass(frozen=True, slots=True)
class StageDetectionResult:
    """Outcome of evaluating stage detection with reason codes and evidence."""

    detected_stage: TaskStage
    precedence_level: int
    reason_codes: list[str] = field(default_factory=list)
    confidence: float = 1.0
    evidence_summary: str = ""


class StageDetector:
    """Deterministic stage detector evaluating facts in strict precedence order."""

    def detect_stage(
        self,
        task: Task,
        runtime_state: RuntimeState,
        latest_turn: UserTurn | None = None,
    ) -> StageDetectionResult:
        """Evaluate deterministic facts and return the detected authoritative stage."""
        curr_stage = task.current_stage
        plan: PlanDAG | None = runtime_state.plan

        # Level 1: Terminal state invariant
        if curr_stage.is_terminal:
            return StageDetectionResult(
                detected_stage=curr_stage,
                precedence_level=1,
                reason_codes=["TERMINAL_STATE_IMMUTABLE"],
                confidence=1.0,
                evidence_summary=f"Task is already in terminal stage {curr_stage.value}",
            )

        # Level 2: Explicit User Directive (cancellation / pause / resume)
        if latest_turn is not None:
            user_text = latest_turn.clean_text.lower().strip()
            if re.search(r"^(stop|cancel|abort|terminate)\b", user_text):
                return StageDetectionResult(
                    detected_stage=TaskStage.CANCELLED,
                    precedence_level=2,
                    reason_codes=["USER_EXPLICIT_CANCEL"],
                    confidence=1.0,
                    evidence_summary=f"User command requested cancellation: '{user_text}'",
                )
            if re.search(r"^(pause|hold on|wait a minute|stand by)\b", user_text):
                return StageDetectionResult(
                    detected_stage=TaskStage.PAUSED,
                    precedence_level=2,
                    reason_codes=["USER_EXPLICIT_PAUSE"],
                    confidence=1.0,
                    evidence_summary=f"User command requested pause: '{user_text}'",
                )
            if curr_stage == TaskStage.PAUSED and re.search(
                r"^(resume|continue|go ahead)\b", user_text
            ):
                return StageDetectionResult(
                    detected_stage=TaskStage.EXECUTION,
                    precedence_level=2,
                    reason_codes=["USER_EXPLICIT_RESUME"],
                    confidence=1.0,
                    evidence_summary=f"User command requested resumption: '{user_text}'",
                )

        if curr_stage == TaskStage.PAUSED:
            return StageDetectionResult(
                detected_stage=TaskStage.PAUSED,
                precedence_level=1,
                reason_codes=["TASK_REMAINS_PAUSED"],
                confidence=1.0,
                evidence_summary="Task is paused awaiting explicit user resume directive",
            )

        # Level 3: Pending Approvals (High/Critical risk nodes awaiting human operator)
        if plan is not None:
            for node in plan.nodes.values():
                if node.status == NodeStatus.WAITING_FOR_APPROVAL:
                    appr = runtime_state.approvals.get(node.node_id)
                    if not appr or appr.status == ApprovalStatus.PENDING:
                        return StageDetectionResult(
                            detected_stage=TaskStage.WAITING_FOR_APPROVAL,
                            precedence_level=3,
                            reason_codes=["PENDING_OPERATOR_APPROVAL"],
                            confidence=1.0,
                            evidence_summary=f"Node {node.node_id} requires operator approval before execution",
                        )

        # Level 4: Active Tool / Subprocess State
        if plan is not None:
            for node in plan.nodes.values():
                if node.status in (NodeStatus.RUNNING, NodeStatus.WAITING_FOR_TOOL):
                    return StageDetectionResult(
                        detected_stage=TaskStage.WAITING_FOR_TOOL,
                        precedence_level=4,
                        reason_codes=["TOOL_EXECUTION_IN_FLIGHT"],
                        confidence=1.0,
                        evidence_summary=f"Node {node.node_id} is running execution payload",
                    )

        # Level 5: Pending Verification (Tool returned observation, verification not evaluated)
        if plan is not None:
            for node in plan.nodes.values():
                if node.status == NodeStatus.VERIFYING:
                    return StageDetectionResult(
                        detected_stage=TaskStage.VERIFICATION,
                        precedence_level=5,
                        reason_codes=["OBSERVATION_AWAITING_VERIFICATION"],
                        confidence=1.0,
                        evidence_summary=f"Node {node.node_id} has observation awaiting verification assertions",
                    )

        # Level 6: Recovery & Replanning (Node failed with retry/recovery potential)
        if plan is not None:
            for node in plan.nodes.values():
                if node.status == NodeStatus.AMBIGUOUS_CRASH_SUSPECT or (
                    node.status == NodeStatus.FAILED and node.can_retry()
                ):
                    return StageDetectionResult(
                        detected_stage=TaskStage.RECOVERY,
                        precedence_level=6,
                        reason_codes=["NODE_RECOVERY_REQUIRED"],
                        confidence=1.0,
                        evidence_summary=f"Node {node.node_id} requires recovery or re-observation",
                    )

        # Level 7: Plan State
        if plan is None or not plan.nodes:
            return StageDetectionResult(
                detected_stage=TaskStage.PLANNING,
                precedence_level=7,
                reason_codes=["NO_ACTIVE_PLAN"],
                confidence=1.0,
                evidence_summary="Task has no execution plan; planning required",
            )

        if plan.is_completed():
            return StageDetectionResult(
                detected_stage=TaskStage.COMPLETED,
                precedence_level=7,
                reason_codes=["ALL_PLAN_NODES_COMPLETED"],
                confidence=1.0,
                evidence_summary="All nodes in the active PlanDAG reached terminal completion",
            )

        if plan.is_failed():
            return StageDetectionResult(
                detected_stage=TaskStage.FAILED,
                precedence_level=7,
                reason_codes=["TERMINAL_NODE_FAILURE"],
                confidence=1.0,
                evidence_summary="Plan contains terminal failed node with exhausted retries",
            )

        # If plan has ready or pending nodes
        ready = plan.get_ready_nodes()
        if ready:
            return StageDetectionResult(
                detected_stage=TaskStage.EXECUTION,
                precedence_level=7,
                reason_codes=["NODES_READY_FOR_DISPATCH"],
                confidence=1.0,
                evidence_summary=f"{len(ready)} node(s) ready for execution dispatch",
            )

        # Level 8: Default Fallback
        return StageDetectionResult(
            detected_stage=TaskStage.EXPLORATION,
            precedence_level=8,
            reason_codes=["DEFAULT_STAGE_EXPLORATION"],
            confidence=0.8,
            evidence_summary="No higher precedence condition met; exploring task environment",
        )


__all__ = ["StageDetectionResult", "StageDetector"]
