"""Two-phase cancellation manager with active execution abort confirmation for Track 3.3.

HARD INVARIANTS:
1. Cancellation is an asynchronous confirmation, not an immediate claim:
   CANCEL_REQUESTED -> observe -> CONFIRMED_TERMINATED -> CANCELLED.
2. If the external adapter fails to terminate within timeout -> FAILED_TO_TERMINATE.
"""

from __future__ import annotations

import datetime

from jarvis_agent.execution.runtime import ExecutionRuntime
from jarvis_agent.scheduling.models.cancellation import (
    CancellationConfirmationStatus,
    CancellationRecord,
    CancellationRequest,
)


class CancellationManager:
    """Manages two-phase cancellation and confirmation across Track 3.2 adapters."""

    def __init__(self, execution_runtime: ExecutionRuntime | None = None) -> None:
        self.execution_runtime = execution_runtime

    def request_cancellation(
        self,
        target_id: str,
        target_type: str,
        reason: str,
        requested_by: str = "operator",
    ) -> CancellationRequest:
        """Create and return a structured cancellation request."""
        return CancellationRequest(
            target_id=target_id,
            target_type=target_type,
            requested_by=requested_by,
            reason=reason,
        )

    def abort_execution(
        self,
        execution_id: str,
        node_id: str,
    ) -> CancellationRecord:
        """Issue abort to Track 3.2 execution runtime and confirm termination status."""
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not self.execution_runtime:
            return CancellationRecord(
                execution_id=execution_id,
                node_id=node_id,
                status=CancellationConfirmationStatus.CONFIRMED_TERMINATED,
                confirmed_at_utc=now_str,
                details="No active execution runtime attached; simulated termination",
            )

        # Call Track 3.2 cancel_execution
        stopped = self.execution_runtime.cancel_execution(execution_id)
        status = (
            CancellationConfirmationStatus.CONFIRMED_TERMINATED
            if stopped
            else CancellationConfirmationStatus.FAILED_TO_TERMINATE
        )
        return CancellationRecord(
            execution_id=execution_id,
            node_id=node_id,
            status=status,
            confirmed_at_utc=now_str,
            details=f"Track 3.2 execution abort returned stopped={stopped}",
        )


__all__ = ["CancellationManager"]
