"""Advisory cancellation command builder for Track 3.5.

Constructs `conversation.turn.cancel` frames with idempotent cancel_request_id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

from jarvis_client.protocol.frames import RPCRequestFrame


@dataclass(frozen=True, slots=True)
class CancellationAcceptance:
    """Immediate acknowledgement of cancellation submission."""

    accepted: bool
    cancellation_request_id: str
    task_id: str
    node_id: str = ""
    requested_at_utc: str = ""
    error_message: str | None = None


def build_cancellation_frame(
    task_id: str,
    node_id: str | None = None,
    reason: str = "User requested cancellation",
    client_cancellation_id: str | None = None,
    client_request_id: str | None = None,
) -> tuple[RPCRequestFrame, str]:
    """Construct standard JSON-RPC 2.0 cancellation request frame."""
    req_id = client_request_id or f"req_cancel_{uuid.uuid4().hex[:12]}"
    cancel_id = client_cancellation_id or f"cancel_{uuid.uuid4().hex[:8]}"

    params: dict[str, Any] = {
        "taskId": task_id,
        "nodeId": node_id or "",
        "reason": reason,
        "cancellationRequestId": cancel_id,
    }

    frame = RPCRequestFrame(
        id=req_id,
        method="conversation.turn.cancel",
        params=params,
    )
    return frame, req_id


def parse_cancellation_acceptance(response_result: Any, request_id: str) -> CancellationAcceptance:
    """Parse cancellation response payload."""
    if not isinstance(response_result, dict):
        return CancellationAcceptance(
            accepted=False,
            cancellation_request_id="",
            task_id="",
            error_message="Invalid gateway response format",
        )

    return CancellationAcceptance(
        accepted=bool(response_result.get("accepted", False)),
        cancellation_request_id=str(response_result.get("cancellationRequestId", "")),
        task_id=str(response_result.get("taskId", "")),
        node_id=str(response_result.get("nodeId", "")),
        requested_at_utc=str(response_result.get("requestedAtUtc", "")),
        error_message=response_result.get("error"),
    )


__all__ = ["CancellationAcceptance", "build_cancellation_frame", "parse_cancellation_acceptance"]
