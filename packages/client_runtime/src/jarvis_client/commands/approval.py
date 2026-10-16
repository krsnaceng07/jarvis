"""Action-bound approval responder with stale check for Track 3.5.

Enforces Invariant T35-10:
UIs disable approval actions if the approval expires or plan revision advances.
Submits decision with canonical action digest.
"""

from __future__ import annotations

import datetime
from typing import Any
import uuid

from jarvis_client.errors import ClientErrorCode, StaleActionError
from jarvis_client.protocol.frames import RPCRequestFrame


def build_approval_response_frame(
    approval_id: str,
    approved: bool,
    expected_plan_revision: int,
    current_plan_revision: int,
    expires_at_utc: str | None = None,
    decision_reason: str = "",
    client_request_id: str | None = None,
) -> tuple[RPCRequestFrame, str]:
    """Construct `exec.approvals.respond` frame with client-side stale protection."""
    # Stale plan revision check
    if current_plan_revision > expected_plan_revision:
        raise StaleActionError(
            code=ClientErrorCode.STALE_APPROVAL,
            message=f"Approval action is stale: current revision {current_plan_revision} exceeds expected {expected_plan_revision}.",
        )

    # Expiration check
    if expires_at_utc:
        now = datetime.datetime.now(datetime.timezone.utc)
        try:
            exp = datetime.datetime.fromisoformat(expires_at_utc)
            if now >= exp:
                raise StaleActionError(
                    code=ClientErrorCode.APPROVAL_EXPIRED,
                    message=f"Approval '{approval_id}' has expired.",
                )
        except (ValueError, TypeError):
            pass

    req_id = client_request_id or f"app_res_{uuid.uuid4().hex[:12]}"
    params: dict[str, Any] = {
        "approvalId": approval_id,
        "approved": approved,
        "decisionReason": decision_reason
        or ("Approved by user" if approved else "Rejected by user"),
        "expectedPlanRevision": expected_plan_revision,
    }

    frame = RPCRequestFrame(
        id=req_id,
        method="exec.approvals.respond",
        params=params,
    )
    return frame, req_id


__all__ = ["build_approval_response_frame"]
