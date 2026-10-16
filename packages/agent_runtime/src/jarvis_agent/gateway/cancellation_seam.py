"""Advisory cancellation transport seam for Track 3.4.

Enforces Invariant T34-09: Cancellation authority remains strictly in Track 3.3/3.2.
Enforces Invariant T34-15: Gateway cancellation acknowledgement means request accepted;
physical cancellation outcome is observed asynchronously.
"""

from __future__ import annotations

import datetime
from typing import Any
import uuid

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import ClientIdentity
from jarvis_agent.scheduling.cancellation.cancellation_manager import CancellationManager


class CancellationGatewaySeam:
    """Bridges client cancellation requests to Track 3.3 CancellationManager."""

    def __init__(self, cancellation_manager: CancellationManager | None = None) -> None:
        self.cancellation_manager = cancellation_manager

    def submit_cancellation_request(
        self,
        task_id: str,
        node_id: str | None,
        reason: str,
        identity: ClientIdentity,
    ) -> dict[str, Any]:
        """Submit advisory cancellation request; returns immediate acceptance frame (Invariant T34-15)."""
        if not identity.has_scope("cancel") and identity.auth_tier != "admin":
            raise GatewayException(
                code=GatewayErrorCode.SESSION_FORBIDDEN,
                message=f"Principal '{identity.user_id}' lacks 'cancel' scope.",
            )

        req_id = f"cancel_req_{uuid.uuid4().hex[:8]}"

        if self.cancellation_manager:
            self.cancellation_manager.request_cancellation(
                target_id=node_id or task_id,
                target_type="node" if node_id else "task",
                reason=reason,
                requested_by=identity.user_id,
            )

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return {
            "accepted": True,
            "cancellationRequestId": req_id,
            "taskId": task_id,
            "nodeId": node_id or "",
            "requestedAtUtc": now_str,
            "reason": reason,
        }


__all__ = ["CancellationGatewaySeam"]
