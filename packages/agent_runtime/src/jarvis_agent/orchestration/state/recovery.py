"""Post-crash state reconciliation and ambiguous execution recovery.

Enforces:
1. Replay from snapshot + uncheckpointed journal events.
2. Nodes in flight at crash time are marked AMBIGUOUS_CRASH_SUSPECT.
3. No side effects are re-executed autonomously without empirical re-observation.
"""

from __future__ import annotations


from jarvis_agent.orchestration.models import NodeStatus
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.orchestration.state.reducer import RuntimeState, reduce_events, reduce_state
from jarvis_agent.orchestration.state.snapshot import SnapshotEngine


class CrashRecoveryManager:
    """Orchestrates deterministic state recovery and in-flight node reconciliation post-crash."""

    def __init__(
        self,
        event_store: EventStore,
        snapshot_engine: SnapshotEngine | None = None,
    ) -> None:
        self._event_store = event_store
        self._snapshot_engine = snapshot_engine

    def recover_task(self, task_id: str) -> tuple[RuntimeState, list[str]]:
        """Recover authoritative task state and flag ambiguous nodes.

        Returns:
            Tuple of (reconstructed RuntimeState, list of ambiguous_node_ids)
        """
        # Step 1: Check for existing snapshot
        snapshot: RuntimeState | None = None
        start_seq = 0
        if self._snapshot_engine is not None:
            snapshot = self._snapshot_engine.load_snapshot(task_id)
            if snapshot is not None:
                start_seq = snapshot.applied_sequence

        # Step 2: Fetch unapplied events from journal
        events = self._event_store.get_events_for_task(task_id, after_sequence=start_seq)
        state = reduce_events(snapshot, events)

        if not state.task or not state.plan:
            return state, []

        # Step 3: Identify nodes that were in-flight when the crash occurred
        ambiguous_node_ids: list[str] = []
        for nid, node in state.plan.nodes.items():
            if node.status in (NodeStatus.RUNNING, NodeStatus.WAITING_FOR_TOOL):
                ambiguous_node_ids.append(nid)

        # Step 4: Emit AMBIGUOUS_CRASH_SUSPECTED events for each in-flight node
        if ambiguous_node_ids:
            curr_seq = self._event_store.get_latest_sequence(task_id)
            reconciliation_events: list[DomainEvent] = []
            for nid in ambiguous_node_ids:
                curr_seq += 1
                evt = DomainEvent.create(
                    task_id=task_id,
                    conversation_id=state.task.identity.conversation_id,
                    event_type=EventType.AMBIGUOUS_CRASH_SUSPECTED,
                    payload={"node_id": nid, "reason": "Crash occurred while node was in-flight"},
                    sequence_number=curr_seq,
                )
                reconciliation_events.append(evt)

            self._event_store.append_batch(reconciliation_events)
            # Replay reconciliation events into final recovered state
            for revt in reconciliation_events:
                state = reduce_state(state, revt)

        return state, ambiguous_node_ids


__all__ = ["CrashRecoveryManager"]
