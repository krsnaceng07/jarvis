"""Master OrchestrationRuntime coordinating event sourcing, stages, brain, DAGs, and recovery."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any
import uuid

from jarvis_agent.orchestration.brain import (
    BrainDecision,
    BrainDecisionType,
    CognitiveBrain,
    DecisionPolicyGate,
)
from jarvis_agent.orchestration.models import (
    Conversation,
    ExecutionCommand,
    ObservationRecord,
    Task,
    TaskIdentity,
    TaskStage,
    UserTurn,
    VerificationResult,
)
from jarvis_agent.orchestration.planning import (
    GoalParser,
    PlanDAGBuilder,
    PlanLimits,
    PlanValidator,
    Replanner,
)
from jarvis_agent.orchestration.recovery import (
    FailureClass,
    RecoveryLoopDetector,
    RetryManager,
)
from jarvis_agent.orchestration.scheduling import (
    SchedulerSeam,
)
from jarvis_agent.orchestration.stage import (
    StageDetector,
    StageTransitionEngine,
)
from jarvis_agent.orchestration.state import (
    CrashRecoveryManager,
    DomainEvent,
    EventStore,
    EventType,
    RuntimeState,
    SnapshotEngine,
    reduce_state,
)
from jarvis_agent.orchestration.task import (
    AmbiguityScorer,
    TaskFocusManager,
    TaskLifecycleManager,
    TaskLineageTracker,
    TaskResolver,
)


class OrchestrationRuntime:
    """Deterministic, crash-resilient orchestration engine for JARVIS."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        enforce_global_operator_approval: bool = False,
    ) -> None:
        self._event_store = EventStore(db_path)
        self._snapshot_engine = SnapshotEngine(db_path) if db_path else None
        self._recovery_mgr = CrashRecoveryManager(self._event_store, self._snapshot_engine)

        self._lineage = TaskLineageTracker()
        self._focus = TaskFocusManager()
        self._scorer = AmbiguityScorer()
        self._resolver = TaskResolver(self._focus, self._scorer)
        self._lifecycle = TaskLifecycleManager()

        self._detector = StageDetector()
        self._transition_engine = StageTransitionEngine(self._event_store, self._detector)

        self._goal_parser = GoalParser()
        self._limits = PlanLimits()
        self._validator = PlanValidator(self._limits)
        self._policy = DecisionPolicyGate(
            enforce_global_operator_approval=enforce_global_operator_approval
        )
        self._brain = CognitiveBrain(self._detector, self._policy, self._goal_parser)

        self._replanner = Replanner()
        self._retry_mgr = RetryManager()
        self._loop_detector = RecoveryLoopDetector()

        # In-memory session tracking
        self._conversations: dict[str, Conversation] = {}
        self._cached_states: dict[str, RuntimeState] = {}

    def recover_after_crash(self, task_id: str) -> tuple[RuntimeState, list[str]]:
        """Recover task state post-crash, reconciling in-flight nodes to AMBIGUOUS_CRASH_SUSPECT."""
        recovered, suspects = self._recovery_mgr.recover_task(task_id)
        self._cached_states[task_id] = recovered
        return recovered, suspects

    def get_state(self, task_id: str) -> RuntimeState:
        """Fetch authoritative reduced state for task_id, reconstructing from journal if needed."""
        if task_id in self._cached_states:
            return self._cached_states[task_id]

        recovered, _ = self._recovery_mgr.recover_task(task_id)
        self._cached_states[task_id] = recovered
        return recovered

    def process_turn(
        self,
        turn: UserTurn,
    ) -> tuple[RuntimeState, BrainDecision, ExecutionCommand | None]:
        """Process inbound normalized user turn through the complete orchestration lifecycle."""
        cid = turn.conversation_id
        conv = self._conversations.get(cid)
        if not conv:
            conv = Conversation(
                conversation_id=cid,
                session_id=turn.session_id,
                channel=turn.response_route.channel,
                user_id=turn.user_id,
            )
            self._conversations[cid] = conv

        self._conversations[cid] = conv.with_turn(turn.turn_id)
        active_tids = list(self._conversations[cid].active_task_ids)

        # 1. Resolve task
        resolution = self._resolver.resolve(turn, active_tids)

        if resolution.action == "CLARIFY":
            dummy_id = f"task_{uuid.uuid4().hex[:8]}"
            dummy_ident = TaskIdentity(
                task_id=dummy_id,
                conversation_id=cid,
                session_id=turn.session_id,
                root_task_id=dummy_id,
                turn_id=turn.turn_id,
                creation_event_id="",
            )
            dummy_task = Task(
                dummy_ident, turn.clean_text, TaskStage.CLARIFICATION, turn.response_route
            )
            decision = BrainDecision(
                decision_type=BrainDecisionType.REQUEST_CLARIFICATION,
                task_id=dummy_id,
                confidence=resolution.confidence,
                is_authorized=True,
                reason=resolution.clarification_prompt or "Clarification required.",
            )
            return RuntimeState(task=dummy_task), decision, None

        if resolution.action == "NEW":
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            ident = TaskIdentity(
                task_id=task_id,
                conversation_id=cid,
                session_id=turn.session_id,
                root_task_id=task_id,
                turn_id=turn.turn_id,
                creation_event_id=f"evt_create_{task_id}",
            )
            task = Task(
                identity=ident,
                goal=resolution.new_goal or turn.clean_text,
                current_stage=TaskStage.PLANNING,
                response_route=turn.response_route,
            )

            # Record creation in journal
            evt = DomainEvent.create(
                task_id=task_id,
                conversation_id=cid,
                event_type=EventType.TASK_CREATED,
                payload={"task": task.to_dict()},
                sequence_number=1,
                timestamp_utc=now_utc,
            )
            self._event_store.append(evt)
            state = reduce_state(None, evt)

            self._lineage.register_task(ident)
            self._focus.push_focus(task_id)
            self._lifecycle.register_task(task_id)
            self._conversations[cid] = self._conversations[cid].with_task(task_id, set_focus=True)
            self._cached_states[task_id] = state

        else:
            task_id = resolution.target_task_id or ""
            state = self.get_state(task_id)
            if not state.task:
                raise ValueError(f"Task {task_id} not found in state.")
            task = state.task
            self._focus.push_focus(task_id)
            self._lifecycle.touch(task_id)

        # 2. Check for immediate stage transitions from user directive (pause, cancel, resume)
        detection = self._detector.detect_stage(task, state, latest_turn=turn)
        if detection.detected_stage != task.current_stage:
            if detection.detected_stage == TaskStage.CANCELLED:
                evt = DomainEvent.create(
                    task_id=task_id,
                    conversation_id=cid,
                    event_type=EventType.TASK_CANCELLED,
                    payload={"reason": detection.evidence_summary},
                    sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
                )
                self._event_store.append(evt)
                state = reduce_state(state, evt)
                self._cached_states[task_id] = state
                if not state.task:
                    raise ValueError("Reduced state missing authoritative task.")
                task = state.task
            elif detection.detected_stage == TaskStage.PAUSED:
                evt = DomainEvent.create(
                    task_id=task_id,
                    conversation_id=cid,
                    event_type=EventType.TASK_PAUSED,
                    payload={"reason": detection.evidence_summary},
                    sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
                )
                self._event_store.append(evt)
                state = reduce_state(state, evt)
                self._cached_states[task_id] = state
                if not state.task:
                    raise ValueError("Reduced state missing authoritative task.")
                task = state.task
            elif (
                detection.detected_stage == TaskStage.EXECUTION
                and task.current_stage == TaskStage.PAUSED
            ):
                evt = DomainEvent.create(
                    task_id=task_id,
                    conversation_id=cid,
                    event_type=EventType.TASK_RESUMED,
                    payload={"reason": detection.evidence_summary},
                    sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
                )
                self._event_store.append(evt)
                state = reduce_state(state, evt)
                self._cached_states[task_id] = state
                if not state.task:
                    raise ValueError("Reduced state missing authoritative task.")
                task = state.task

        # 3. Cognitive Brain Decision
        decision = self._brain.decide(task, state, latest_turn=turn)

        # 3. If decision is PROPOSE_PLAN, automatically build and register DAG
        command: ExecutionCommand | None = None
        if decision.decision_type == BrainDecisionType.PROPOSE_PLAN:
            parsed = self._goal_parser.parse(task.goal)
            builder = PlanDAGBuilder(self._validator)

            if parsed.primary_intent == "PLAY_MEDIA":
                media_target = parsed.target_entities[0] if parsed.target_entities else "lofi"
                builder.add_node(
                    "n_open", "Open browser", "browser.navigate", {"url": "https://youtube.com"}
                )
                builder.add_node(
                    "n_search",
                    f"Search for {media_target}",
                    "browser.search",
                    {"query": media_target},
                    dependencies=["n_open"],
                )
                builder.add_node(
                    "n_play",
                    "Play first result",
                    "browser.click",
                    {"selector": "#video-title"},
                    dependencies=["n_search"],
                )
                self._focus.register_entities(
                    task_id, {"url": "https://youtube.com", "media": media_target}
                )
            else:
                builder.add_node(
                    "n_1", f"Execute goal: {task.goal}", "system.run", {"goal": task.goal}
                )

            plan = builder.build(task_id=task_id)
            plan_evt = DomainEvent.create(
                task_id=task_id,
                conversation_id=cid,
                event_type=EventType.PLAN_CREATED,
                payload={"plan": plan.to_dict()},
                sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
            )
            self._event_store.append(plan_evt)
            state = reduce_state(state, plan_evt)

            # Advance stage to EXECUTION
            state, _ = self._transition_engine.transition(
                state, TaskStage.EXECUTION, ["PLAN_PROPOSED_AND_BOUND"]
            )
            self._cached_states[task_id] = state

            # Formulate immediate execution decision
            decision = self._brain.decide(state.task, state)  # type: ignore[arg-type]

        # 4. If decision is EXECUTE_NODE, issue command via SchedulerSeam
        if (
            decision.decision_type == BrainDecisionType.EXECUTE_NODE
            and decision.is_authorized
            and decision.node_id
        ):
            node = state.plan.nodes[decision.node_id]  # type: ignore[union-attr]
            command = SchedulerSeam.create_command(
                task=state.task,  # type: ignore[arg-type]
                plan_id=state.plan.plan_id,  # type: ignore[union-attr]
                plan_revision=state.plan.revision,  # type: ignore[union-attr]
                node=node,
            )
            # Record NODE_STARTED
            start_evt = DomainEvent.create(
                task_id=task_id,
                conversation_id=cid,
                event_type=EventType.NODE_STARTED,
                payload={"node_id": node.node_id, "execution_id": command.execution_id},
                sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
            )
            self._event_store.append(start_evt)
            state = reduce_state(state, start_evt)

            # Advance stage to WAITING_FOR_TOOL
            state, _ = self._transition_engine.transition(
                state, TaskStage.WAITING_FOR_TOOL, ["COMMAND_DISPATCHED_TO_SEAM"]
            )
            self._cached_states[task_id] = state

        return state, decision, command

    def handle_observation(
        self,
        task_id: str,
        node_id: str,
        observation: ObservationRecord,
        verification: VerificationResult,
    ) -> RuntimeState:
        """Process empirical observation and verification result from tool execution."""
        state = self.get_state(task_id)
        cid = state.task.identity.conversation_id  # type: ignore[union-attr]

        # Record observation
        obs_evt = DomainEvent.create(
            task_id=task_id,
            conversation_id=cid,
            event_type=EventType.NODE_OBSERVED,
            payload={"node_id": node_id, "observation": observation.to_dict()},
            sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
        )
        self._event_store.append(obs_evt)
        state = reduce_state(state, obs_evt)

        # Record verification
        ver_evt = DomainEvent.create(
            task_id=task_id,
            conversation_id=cid,
            event_type=EventType.NODE_VERIFIED,
            payload={"node_id": node_id, "verification_result": verification.to_dict()},
            sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
        )
        self._event_store.append(ver_evt)
        state = reduce_state(state, ver_evt)

        # Evaluate next stage
        next_det = self._detector.detect_stage(state.task, state)  # type: ignore[arg-type]
        if next_det.detected_stage != state.task.current_stage:  # type: ignore[union-attr]
            state, _ = self._transition_engine.transition(
                state, next_det.detected_stage, next_det.reason_codes
            )

        self._cached_states[task_id] = state
        return state

    def handle_approval(
        self,
        task_id: str,
        node_id: str,
        granted: bool,
        operator_id: str | None = None,
        reason: str | None = None,
    ) -> RuntimeState:
        """Handle human operator approval decision."""
        state = self.get_state(task_id)
        cid = state.task.identity.conversation_id  # type: ignore[union-attr]
        evt_type = EventType.APPROVAL_GRANTED if granted else EventType.APPROVAL_DENIED
        payload = {"node_id": node_id, "operator_id": operator_id, "decision_reason": reason}

        evt = DomainEvent.create(
            task_id=task_id,
            conversation_id=cid,
            event_type=evt_type,
            payload=payload,
            sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
        )
        self._event_store.append(evt)
        state = reduce_state(state, evt)

        # Transition stage
        target_stage = TaskStage.EXECUTION if granted else TaskStage.FAILED
        state, _ = self._transition_engine.transition(
            state, target_stage, [f"APPROVAL_{'GRANTED' if granted else 'DENIED'}"]
        )
        self._cached_states[task_id] = state
        return state

    def handle_failure(
        self,
        task_id: str,
        node_id: str,
        failure_class: FailureClass,
        error_message: str,
    ) -> tuple[RuntimeState, BrainDecision]:
        """Handle node failure, checking for loop detection and triggering replan."""
        state = self.get_state(task_id)
        cid = state.task.identity.conversation_id  # type: ignore[union-attr]
        node = state.plan.nodes[node_id]  # type: ignore[union-attr]

        # Check loop detection
        loop_res = self._loop_detector.record_and_check(node_id, node.arguments, failure_class)
        if loop_res.is_loop:
            # Fatal loop detected: terminate task
            fail_evt = DomainEvent.create(
                task_id=task_id,
                conversation_id=cid,
                event_type=EventType.NODE_FAILED,
                payload={"node_id": node_id, "error_message": loop_res.message},
                sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
            )
            self._event_store.append(fail_evt)
            state = reduce_state(state, fail_evt)
            state, _ = self._transition_engine.transition(
                state, TaskStage.FAILED, ["RECOVERY_LOOP_HALTED"]
            )
            self._cached_states[task_id] = state
            decision = BrainDecision(
                decision_type=BrainDecisionType.FAIL_TASK,
                task_id=task_id,
                node_id=node_id,
                confidence=1.0,
                is_authorized=True,
                reason=loop_res.message,
            )
            return state, decision

        # Non-loop failure: transition to RECOVERY and trigger replan
        fail_evt = DomainEvent.create(
            task_id=task_id,
            conversation_id=cid,
            event_type=EventType.NODE_FAILED,
            payload={"node_id": node_id, "error_message": error_message},
            sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
        )
        self._event_store.append(fail_evt)
        state = reduce_state(state, fail_evt)
        state, _ = self._transition_engine.transition(
            state, TaskStage.RECOVERY, ["NODE_FAILED_AWAITING_REPLAN"]
        )

        # Execute replanning
        new_plan, _diff, revision = self._replanner.replan(
            current_plan=state.plan,  # type: ignore[arg-type]
            failed_node_id=node_id,
            reason=error_message,
        )
        rev_evt = DomainEvent.create(
            task_id=task_id,
            conversation_id=cid,
            event_type=EventType.PLAN_REVISED,
            payload={"plan": new_plan.to_dict(), "revision": revision.to_dict()},
            sequence_number=self._event_store.get_latest_sequence(task_id) + 1,
        )
        self._event_store.append(rev_evt)
        state = reduce_state(state, rev_evt)

        # Resume execution
        state, _ = self._transition_engine.transition(
            state, TaskStage.EXECUTION, ["REPLAN_APPLIED"]
        )
        self._cached_states[task_id] = state

        decision = self._brain.decide(state.task, state)  # type: ignore[arg-type]
        return state, decision

    def close(self) -> None:
        """Close SQLite database connections."""
        self._event_store.close()
        if self._snapshot_engine:
            self._snapshot_engine.close()

    def __enter__(self) -> OrchestrationRuntime:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


__all__ = ["OrchestrationRuntime"]
