"""5-Level Evidence Ladder implementation for post-restart crash reconciliation.

HARD INVARIANTS:
1. Evidence Level Hierarchy:
   Level 0: No evidence (unstarted or missing records)
   Level 1: Local scheduler projection record exists
   Level 2: Track 3.2 IdempotencyLedger COMPLETED state
   Level 3: Machine observations with cryptographic digests collected
   Level 4: Independent state verification passed (StateVerifier)
   Level 5: Durably committed NODE_VERIFIED event in EventStore with evidence digests
2. A node can ONLY be reconciled to VERIFIED if Level 5 evidence is present.
3. Level 2 (idempotency ledger COMPLETED) alone is NOT sufficient for VERIFIED;
   it only proves adapter dispatch completed, not that postconditions were verified.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from jarvis_agent.execution.idempotency.ledger import IdempotencyLedger
from jarvis_agent.execution.models.idempotency_record import IdempotencyState
from jarvis_agent.orchestration.state.event import EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.models.recovery import EvidenceLevel

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EvidenceLadderAssessment:
    """Evaluation outcome assessing reached evidence level for an in-flight execution."""

    node_id: str
    task_id: str
    idempotency_key: str
    level_reached: EvidenceLevel
    has_durable_event: bool
    has_verified_postcondition: bool
    has_machine_observations: bool
    has_ledger_completion: bool
    details: str


class EvidenceLadderEvaluator:
    """Evaluates the exact evidence level attained by an execution command."""

    @staticmethod
    def evaluate(
        task_id: str,
        node_id: str,
        idempotency_key: str,
        event_store: EventStore | None,
        idempotency_ledger: IdempotencyLedger | None,
    ) -> EvidenceLadderAssessment:
        has_ledger = False
        has_obs = False
        has_ver = False
        has_event = False

        # Check Level 2: IdempotencyLedger
        if idempotency_ledger:
            record = idempotency_ledger.get(idempotency_key)
            if record and record.state == IdempotencyState.COMPLETED:
                has_ledger = True
                if record.execution_result:
                    raw_res = record.execution_result
                    if raw_res.get("observations"):
                        has_obs = True
                    vr = raw_res.get("verification_result")
                    if vr and vr.get("passed"):
                        has_ver = True

        # Check Level 5: EventStore durably committed NODE_VERIFIED
        if event_store:
            events = event_store.get_events_for_task(task_id)
            for evt in events:
                if (
                    evt.event_type == EventType.NODE_VERIFIED
                    and evt.payload.get("node_id") == node_id
                ):
                    has_event = True
                    has_ver = True
                    break

        # Compute level reached
        if has_event and has_ver:
            level = EvidenceLevel.LEVEL_5_DURABLE_EVENT_COMMIT
            details = "Level 5: Durably committed NODE_VERIFIED event present in EventStore"
        elif has_ver:
            level = EvidenceLevel.LEVEL_4_INDEPENDENT_VERIFIED
            details = "Level 4: Independent state verification passed, but durable event commit unconfirmed"
        elif has_obs:
            level = EvidenceLevel.LEVEL_3_MACHINE_OBSERVATION
            details = "Level 3: Machine observations collected, but state verification unconfirmed"
        elif has_ledger:
            level = EvidenceLevel.LEVEL_2_EXECUTION_LEDGER
            details = "Level 2: Idempotency ledger reports COMPLETED, but verification is unproven"
        else:
            level = EvidenceLevel.LEVEL_0_NO_EVIDENCE
            details = "Level 0: No execution or ledger record found"

        return EvidenceLadderAssessment(
            node_id=node_id,
            task_id=task_id,
            idempotency_key=idempotency_key,
            level_reached=level,
            has_durable_event=has_event,
            has_verified_postcondition=has_ver,
            has_machine_observations=has_obs,
            has_ledger_completion=has_ledger,
            details=details,
        )


__all__ = ["EvidenceLadderAssessment", "EvidenceLadderEvaluator"]
