"""Stage transition execution engine enforcing legal transitions and event emission."""

from __future__ import annotations

import datetime
import uuid

from jarvis_agent.orchestration.models import StageTransition, TaskStage
from jarvis_agent.orchestration.stage.detector import StageDetector
from jarvis_agent.orchestration.stage.transition_rules import (
    validate_transition,
)
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.orchestration.state.reducer import RuntimeState, reduce_state


class StageTransitionEngine:
    """Executes validated stage transitions and records authoritative journal events."""

    def __init__(
        self,
        event_store: EventStore,
        detector: StageDetector | None = None,
    ) -> None:
        self._event_store = event_store
        self._detector = detector or StageDetector()

    def transition(
        self,
        runtime_state: RuntimeState,
        target_stage: TaskStage,
        reason_codes: list[str],
        confidence: float = 1.0,
        evidence_refs: list[str] | None = None,
        initiator: str = "TRANSITION_ENGINE",
    ) -> tuple[RuntimeState, StageTransition]:
        """Execute a transition to target_stage if legal according to the transition matrix."""
        if not runtime_state.task:
            raise ValueError("Cannot transition stage on a RuntimeState with no Task.")

        task = runtime_state.task
        current_stage = task.current_stage

        # Validate legal transition
        validate_transition(current_stage, target_stage)

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        trans_id = f"trans_{uuid.uuid4().hex[:12]}"
        transition_record = StageTransition(
            transition_id=trans_id,
            task_id=task.task_id,
            previous_stage=current_stage,
            new_stage=target_stage,
            reason_codes=reason_codes,
            confidence=confidence,
            evidence_refs=evidence_refs or [],
            timestamp_utc=now_utc,
            initiator=initiator,
        )

        next_seq = self._event_store.get_latest_sequence(task.task_id) + 1
        event = DomainEvent.create(
            task_id=task.task_id,
            conversation_id=task.identity.conversation_id,
            event_type=EventType.STAGE_CHANGED,
            payload={
                "previous_stage": current_stage.value,
                "new_stage": target_stage.value,
                "transition": transition_record.to_dict(),
            },
            sequence_number=next_seq,
            timestamp_utc=now_utc,
        )

        self._event_store.append(event)
        new_state = reduce_state(runtime_state, event)
        return new_state, transition_record


__all__ = ["StageTransitionEngine"]
