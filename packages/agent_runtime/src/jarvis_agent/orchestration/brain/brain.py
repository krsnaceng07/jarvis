"""CognitiveBrain coordinator synthesizing stage detection, planning, and policy gating."""

from __future__ import annotations

from jarvis_agent.orchestration.brain.confidence import ConfidenceEvaluator
from jarvis_agent.orchestration.brain.decision import BrainDecision, BrainDecisionType
from jarvis_agent.orchestration.brain.decision_policy import DecisionPolicyGate
from jarvis_agent.orchestration.models import Task, TaskStage, UserTurn
from jarvis_agent.orchestration.planning.goal_parser import GoalParser
from jarvis_agent.orchestration.stage.detector import StageDetector
from jarvis_agent.orchestration.state.reducer import RuntimeState


class CognitiveBrain:
    """Central cognitive engine formulating structured BrainDecisions."""

    def __init__(
        self,
        stage_detector: StageDetector | None = None,
        policy_gate: DecisionPolicyGate | None = None,
        goal_parser: GoalParser | None = None,
    ) -> None:
        self._detector = stage_detector or StageDetector()
        self._policy = policy_gate or DecisionPolicyGate()
        self._parser = goal_parser or GoalParser()

    def decide(
        self,
        task: Task,
        runtime_state: RuntimeState,
        latest_turn: UserTurn | None = None,
    ) -> BrainDecision:
        """Formulate the next authorized cognitive decision for the task."""
        detection = self._detector.detect_stage(task, runtime_state, latest_turn)
        current_stage = detection.detected_stage
        task_id = task.task_id

        if current_stage == TaskStage.PLANNING:
            parsed = self._parser.parse(task.goal)
            confidence = ConfidenceEvaluator.evaluate_epistemic_confidence(parsed)
            return BrainDecision(
                decision_type=BrainDecisionType.PROPOSE_PLAN,
                task_id=task_id,
                confidence=confidence,
                is_authorized=True,
                reason="Task requires plan proposal decomposition.",
                payload={"parsed_goal": parsed.to_dict()},
            )

        elif current_stage == TaskStage.EXECUTION:
            plan = runtime_state.plan
            if not plan:
                return BrainDecision(
                    decision_type=BrainDecisionType.PROPOSE_PLAN,
                    task_id=task_id,
                    confidence=1.0,
                    is_authorized=True,
                    reason="Plan missing in execution stage; replanning required.",
                )

            ready_nodes = plan.get_ready_nodes()
            if not ready_nodes:
                return BrainDecision(
                    decision_type=BrainDecisionType.NO_OP,
                    task_id=task_id,
                    confidence=1.0,
                    is_authorized=True,
                    reason="No nodes currently ready for execution dispatch.",
                )

            candidate_node = ready_nodes[0]
            auth_result = self._policy.authorize_node_execution(candidate_node, runtime_state)

            if auth_result.is_authorized:
                return BrainDecision(
                    decision_type=BrainDecisionType.EXECUTE_NODE,
                    task_id=task_id,
                    node_id=candidate_node.node_id,
                    confidence=1.0,
                    is_authorized=True,
                    reason=auth_result.reason,
                    payload={
                        "capability": candidate_node.capability,
                        "arguments": candidate_node.arguments,
                    },
                )
            else:
                return BrainDecision(
                    decision_type=BrainDecisionType.REQUEST_APPROVAL,
                    task_id=task_id,
                    node_id=candidate_node.node_id,
                    confidence=1.0,
                    is_authorized=False,
                    reason=auth_result.reason,
                    payload={
                        "risk_assessment": candidate_node.risk_assessment.to_dict(),
                        "arguments": candidate_node.arguments,
                    },
                )

        elif current_stage == TaskStage.WAITING_FOR_APPROVAL:
            return BrainDecision(
                decision_type=BrainDecisionType.REQUEST_APPROVAL,
                task_id=task_id,
                confidence=1.0,
                is_authorized=False,
                reason="Task is waiting for operator approval.",
            )

        elif current_stage == TaskStage.CLARIFICATION:
            return BrainDecision(
                decision_type=BrainDecisionType.REQUEST_CLARIFICATION,
                task_id=task_id,
                confidence=detection.confidence,
                is_authorized=True,
                reason="User clarification required before proceeding.",
            )

        elif current_stage == TaskStage.RECOVERY:
            return BrainDecision(
                decision_type=BrainDecisionType.REPLAN,
                task_id=task_id,
                confidence=1.0,
                is_authorized=True,
                reason="Node failure or crash detected; replanning required.",
            )

        elif current_stage == TaskStage.COMPLETED:
            return BrainDecision(
                decision_type=BrainDecisionType.COMPLETE_TASK,
                task_id=task_id,
                confidence=1.0,
                is_authorized=True,
                reason="All plan nodes verified and completed successfully.",
            )

        elif current_stage in (TaskStage.FAILED, TaskStage.CANCELLED):
            return BrainDecision(
                decision_type=BrainDecisionType.FAIL_TASK,
                task_id=task_id,
                confidence=1.0,
                is_authorized=True,
                reason=f"Task terminated in stage {current_stage.value}.",
            )

        return BrainDecision(
            decision_type=BrainDecisionType.NO_OP,
            task_id=task_id,
            confidence=1.0,
            is_authorized=True,
            reason=f"Stage {current_stage.value} in steady state.",
        )


__all__ = ["CognitiveBrain"]
