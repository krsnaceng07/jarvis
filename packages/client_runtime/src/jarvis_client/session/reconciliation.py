"""Request crash-ambiguity reconciliation for Track 3.5.

Enforces Invariant T35-14: Request Outcome Reconciliation.
A mutating request whose outcome is ambiguous (e.g. socket drop before response)
must be reconciled against GatewayRequestLedger before any resubmission.
UNKNOWN is NOT permission to retry. Resubmission is permitted only when authoritative state proves NOT_ADMITTED.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable


class RequestOutcomeStatus(str, Enum):
    """Authoritative outcome status of a client request."""

    NOT_ADMITTED = "not_admitted"
    ADMITTED = "admitted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class RequestReconciler:
    """Reconciles in-flight mutating requests across connection loss and restarts."""

    def __init__(
        self,
        query_status_fn: Callable[[str], dict[str, Any]],
    ) -> None:
        self.query_status_fn = query_status_fn

    def reconcile_request(self, request_id: str) -> tuple[RequestOutcomeStatus, Any]:
        """Query server-authoritative request status and determine actionable outcome."""
        try:
            res = self.query_status_fn(request_id)
            status_str = res.get("status", "unknown").lower()
            payload = res.get("response") or res.get("result")
            status = RequestOutcomeStatus(status_str)
        except Exception:
            status = RequestOutcomeStatus.UNKNOWN
            payload = None

        return status, payload

    def is_safe_to_resubmit(self, status: RequestOutcomeStatus) -> bool:
        """Enforce strict retry gate: only NOT_ADMITTED permits new submission."""
        return status == RequestOutcomeStatus.NOT_ADMITTED


__all__ = ["RequestOutcomeStatus", "RequestReconciler"]
