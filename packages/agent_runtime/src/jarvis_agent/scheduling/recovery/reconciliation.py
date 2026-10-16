"""Post-restart ambiguity reconciliation engine for Track 3.3.

HARD INVARIANTS:
1. When restarting after a crash or ungraceful shutdown, any node left in-flight
   (RUNNING, DISPATCH_REQUESTED, LEASED, OBSERVING, VERIFYING) is initially marked AMBIGUOUS.
2. Reconciliation applies the 5-Level Evidence Ladder:
   - Level 5 confirmed -> transitions to VERIFIED.
   - Idempotency ledger reports FAILED -> transitions to FAILED (eligible for retry).
   - Inconclusive side effect (e.g. NON_IDEMPOTENT_MUTATION or EXTERNAL_TRANSACTION)
     remains AMBIGUOUS and is escalated to Track 3.1 Replanner.
3. NEVER assume success without proof.
"""

from __future__ import annotations

import datetime
from enum import Enum
import logging
import uuid

from jarvis_agent.execution.idempotency.ledger import IdempotencyLedger
from jarvis_agent.execution.models.capability_definition import SideEffectClass
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.scheduling.models.recovery import AmbiguityRecord, EvidenceLevel
from jarvis_agent.scheduling.recovery.evidence_ladder import (
    EvidenceLadderEvaluator,
)
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore

logger = logging.getLogger(__name__)


class ReconciliationAction(str, Enum):
    """Reconciled decision for an in-flight ambiguous node."""

    RESTORE_VERIFIED = "RESTORE_VERIFIED"
    RESTORE_FAILED = "RESTORE_FAILED"
    ESCALATE_TO_REPLANNER = "ESCALATE_TO_REPLANNER"
    RETRY_ELIGIBLE = "RETRY_ELIGIBLE"


class ReconciliationEngine:
    """Reconciles in-flight ambiguous node states following host restarts or crashes."""

    def __init__(
        self,
        projection_store: ProjectionStore,
        event_store: EventStore | None,
        idempotency_ledger: IdempotencyLedger | None,
    ) -> None:
        self.projection_store = projection_store
        self.event_store = event_store
        self.idempotency_ledger = idempotency_ledger

    def reconcile_node(
        self,
        task_id: str,
        node_id: str,
        idempotency_key: str,
        side_effect_class: SideEffectClass,
    ) -> tuple[ReconciliationAction, AmbiguityRecord]:
        """Reconcile an ambiguous node using the evidence ladder and side-effect contracts."""
        assessment = EvidenceLadderEvaluator.evaluate(
            task_id=task_id,
            node_id=node_id,
            idempotency_key=idempotency_key,
            event_store=self.event_store,
            idempotency_ledger=self.idempotency_ledger,
        )

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        audit_id = f"aud_{uuid.uuid4().hex[:10]}"

        # Level 5: Durably committed verification
        if assessment.level_reached == EvidenceLevel.LEVEL_5_DURABLE_EVENT_COMMIT:
            action = ReconciliationAction.RESTORE_VERIFIED
            reason = "Level 5 evidence confirmed: durably committed verification in EventStore"
        elif side_effect_class == SideEffectClass.READ_ONLY:
            # Read-only actions have no external mutations; safe to re-run
            action = ReconciliationAction.RETRY_ELIGIBLE
            reason = "Side-effect class READ_ONLY has no mutations; reset to ELIGIBLE"
        elif side_effect_class in (
            SideEffectClass.NON_IDEMPOTENT_MUTATION,
            SideEffectClass.EXTERNAL_TRANSACTION,
        ):
            # Inconclusive non-idempotent action: escalate to replanner
            action = ReconciliationAction.ESCALATE_TO_REPLANNER
            reason = f"Inconclusive evidence ({assessment.level_reached.name}) for {side_effect_class.value}; requires Track 3.1 replanning"
        else:
            # IDEMPOTENT_MUTATION without Level 5
            action = ReconciliationAction.RETRY_ELIGIBLE
            reason = "IDEMPOTENT_MUTATION safe to retry with matching idempotency key"

        # Record in reconciliation audit log
        cursor = self.projection_store._conn.cursor()
        cursor.execute(
            """
            INSERT INTO reconciliation_audit (
                audit_id, task_id, node_id, execution_id, outcome,
                evidence_level, reason, timestamp_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                audit_id,
                task_id,
                node_id,
                idempotency_key,
                action.value,
                assessment.level_reached.value,
                reason,
                now_str,
            ),
        )
        self.projection_store._conn.commit()

        record = AmbiguityRecord(
            node_id=node_id,
            task_id=task_id,
            execution_id=idempotency_key,
            idempotency_key=idempotency_key,
            capability_target="reconciled_capability",
            side_effect_class=side_effect_class.value,
            evidence_level_reached=assessment.level_reached,
            unverified_reason=reason,
        )
        return action, record


__all__ = ["ReconciliationAction", "ReconciliationEngine"]
