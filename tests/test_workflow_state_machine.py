"""tests.test_workflow_state_machine — Unit tests for WorkflowStateMachine."""

import pytest
from src.agents.task.workflow_state_machine import (
    ProgressEvent,
    WorkflowState,
    WorkflowStateMachine,
)


def test_state_machine_initialization():
    sm = WorkflowStateMachine()
    assert sm.current_state == WorkflowState.IDLE
    assert sm.task_id is None
    assert len(sm.event_history) == 0


def test_valid_transitions():
    sm = WorkflowStateMachine()
    # IDLE -> UNDERSTANDING
    assert sm.can_transition(WorkflowState.UNDERSTANDING)
    evt1 = sm.transition(WorkflowState.UNDERSTANDING, message="Heard input")
    assert sm.current_state == WorkflowState.UNDERSTANDING
    assert evt1.previous_state == WorkflowState.IDLE
    assert evt1.new_state == WorkflowState.UNDERSTANDING

    # UNDERSTANDING -> CLASSIFYING_REQUEST
    assert sm.can_transition(WorkflowState.CLASSIFYING_REQUEST)
    sm.transition(WorkflowState.CLASSIFYING_REQUEST)

    # CLASSIFYING_REQUEST -> RESOLVING_CONTEXT
    assert sm.can_transition(WorkflowState.RESOLVING_CONTEXT)
    sm.transition(WorkflowState.RESOLVING_CONTEXT)

    # RESOLVING_CONTEXT -> PLANNING
    assert sm.can_transition(WorkflowState.PLANNING)
    sm.transition(WorkflowState.PLANNING)

    # PLANNING -> EXECUTING
    assert sm.can_transition(WorkflowState.EXECUTING)
    sm.transition(WorkflowState.EXECUTING)

    # EXECUTING -> OBSERVING
    assert sm.can_transition(WorkflowState.OBSERVING)
    sm.transition(WorkflowState.OBSERVING)

    # OBSERVING -> VERIFYING
    assert sm.can_transition(WorkflowState.VERIFYING)
    sm.transition(WorkflowState.VERIFYING)

    # VERIFYING -> COMPLETED
    assert sm.can_transition(WorkflowState.COMPLETED)
    sm.transition(WorkflowState.COMPLETED)

    # COMPLETED -> IDLE
    assert sm.can_transition(WorkflowState.IDLE)
    sm.transition(WorkflowState.IDLE)
    assert sm.current_state == WorkflowState.IDLE


def test_invalid_transition_raises():
    sm = WorkflowStateMachine()
    assert not sm.can_transition(WorkflowState.COMPLETED)
    with pytest.raises(ValueError, match="Invalid workflow transition"):
        sm.transition(WorkflowState.COMPLETED)


def test_event_listeners():
    sm = WorkflowStateMachine()
    events = []

    def on_progress(evt: ProgressEvent):
        events.append(evt)

    sm.add_listener(on_progress)
    sm.transition(WorkflowState.UNDERSTANDING)
    assert len(events) == 1
    assert events[0].new_state == WorkflowState.UNDERSTANDING

    sm.remove_listener(on_progress)
    sm.transition(WorkflowState.CLASSIFYING_REQUEST)
    assert len(events) == 1  # Not called after removal


def test_format_status_snapshot():
    sm = WorkflowStateMachine()
    sm.attach_task("task-123", step_index=2, total_steps=5)
    sm.transition(WorkflowState.UNDERSTANDING)
    snap = sm.format_status_snapshot()
    assert snap["state"] == "UNDERSTANDING"
    assert snap["task_id"] == "task-123"
    assert snap["step_index"] == 2
    assert snap["total_steps"] == 5
    assert snap["seconds_in_state"] >= 0.0
    assert len(snap["recent_events"]) == 1
